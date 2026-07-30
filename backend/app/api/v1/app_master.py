"""App Master routes — admin-only view + edit of the BigQuery ``app_master_v2`` table.

Every route is gated on ``admin_panel`` (executive/viewer/etc. get 403). Edits touch only
the owner-approved editable columns, write to BigQuery FIRST then the Postgres serving copy,
and are audit-logged. A refresh re-pulls the whole table from BigQuery.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, DbSession, require_capability
from app.core.config import get_settings
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.schemas.app_master import (
    AppMasterEditOut,
    AppMasterFilterValues,
    AppMasterListResponse,
    AppMasterUpdate,
    ColumnOrderUpdate,
)
from app.schemas.integration import SchemaDiff, SchemaSyncResult
from app.services import app_master_service, notification_service
from app.services.app_master_bq import (
    BigQueryNotConfigured,
    BigQueryReadError,
    BigQueryUnavailable,
    BigQueryWriteError,
)
from app.services.audit import AuditDep

router = APIRouter(
    prefix="/app-master",
    tags=["app-master"],
    dependencies=[Depends(enforce_rate_limit), Depends(require_capability("admin_panel"))],
)


@router.get("", response_model=AppMasterListResponse)
async def list_app_master(
    context: CurrentUser,
    db: DbSession,
    search: str | None = None,
    platform: Annotated[list[str], Query()] = [],  # noqa: B006 — FastAPI multi-value query
    hou: Annotated[list[str], Query()] = [],  # noqa: B006
    publisher: Annotated[list[str], Query()] = [],  # noqa: B006
    pod: int | None = None,
    needs_review: bool | None = None,
    package: str | None = None,
    app_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AppMasterListResponse:
    """List rows with the App Master page's own filters (search / platform / HOU / publisher /
    pod / needs-review / package / app-id). Multi-select filters accept repeated params."""
    return await app_master_service.list_rows(
        db,
        search=search,
        platform=platform,
        hou=hou,
        publisher=publisher,
        pod=pod,
        needs_review=needs_review,
        package=package,
        app_id=app_id,
        limit=limit,
        offset=offset,
    )


@router.get("/filter-values", response_model=AppMasterFilterValues)
async def app_master_filter_values(context: CurrentUser, db: DbSession) -> AppMasterFilterValues:
    """Distinct values for the filter dropdowns (platforms / HOU / publishers / pods)."""
    return await app_master_service.filter_values(db)


@router.get("/column-order", response_model=list[str])
async def get_column_order(context: CurrentUser, db: DbSession) -> list[str]:
    """The current global column order."""
    return await app_master_service.get_column_order(db)


@router.put("/column-order", response_model=list[str])
async def set_column_order(
    body: ColumnOrderUpdate, request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> list[str]:
    """Set the GLOBAL column order (admin-only) — applies to every user's App Master grid."""
    order = await app_master_service.set_column_order(db, body.order, context.user_id)
    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_app_master_column_order",
        resource="app_master",
        detail={"order": order},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return order


@router.get("/{key}/history", response_model=list[AppMasterEditOut])
async def app_master_history(
    key: str, context: CurrentUser, db: DbSession
) -> list[AppMasterEditOut]:
    """Change history for one app (newest first)."""
    return await app_master_service.list_history(db, key)


@router.post("/{key}/undo", response_model=dict)
async def undo_app_master(
    key: str, request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> dict[str, Any]:
    """Undo the most recent edit on this row (restores the prior values in BigQuery + PG)."""
    try:
        updated = await app_master_service.undo_last_edit(db, get_settings(), key, context.user_id)
    except app_master_service.NoEditToUndo as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing to undo for this app") from exc
    except app_master_service.AppMasterRowNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "App not found") from exc
    except (BigQueryNotConfigured, BigQueryUnavailable) as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "BigQuery write-back is not configured."
        ) from exc
    except BigQueryWriteError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_undo_app_master",
        resource=key,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return updated


@router.get("/schema-diff", response_model=SchemaDiff)
async def app_master_schema_diff(context: CurrentUser, db: DbSession) -> SchemaDiff:
    """Read-only check that the configured BigQuery table's columns match the registry."""
    return await app_master_service.schema_diff(db, get_settings())


@router.post("/schema-sync", response_model=SchemaSyncResult)
async def app_master_schema_sync(
    request: Request, context: CurrentUser, db: DbSession, audit: AuditDep
) -> SchemaSyncResult:
    """Match Database & BigQuery Schema: additively update the Postgres App Master table to
    the live BigQuery schema (add new columns read-only, heal missing static columns, flag
    vanished ones). Never drops data. Admin-only + audit-logged."""
    try:
        result = await app_master_service.reconcile_schema(db, get_settings(), context.user_id)
    except (BigQueryNotConfigured, BigQueryUnavailable) as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "BigQuery is not configured."
        ) from exc
    except BigQueryReadError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_app_master_schema_sync",
        resource="app_master",
        detail=result.model_dump(mode="json"),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if result.added or result.deactivated:
        await notification_service.notify_admins(
            type="app_master_schema_sync",
            title="App Master schema updated from BigQuery",
            body=(
                f"Added {len(result.added)} column(s), "
                f"flagged {len(result.deactivated)} removed"
            ),
            actor_id=context.user_id,
            resource="app_master",
        )
    return result


@router.patch("/{key}", response_model=dict)
async def update_app_master(
    key: str,
    body: AppMasterUpdate,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> dict[str, Any]:
    """Edit one row's editable columns — writes to BigQuery first, then the serving copy."""
    changes = body.model_dump(exclude_unset=True)
    try:
        updated = await app_master_service.update_row(
            db, get_settings(), key, changes, editor_id=context.user_id
        )
    except app_master_service.AppMasterRowNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "App not found") from exc
    except (BigQueryNotConfigured, BigQueryUnavailable) as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "BigQuery write-back is not configured — no changes were saved.",
        ) from exc
    except BigQueryWriteError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_edit_app_master",
        resource=key,
        detail=body.model_dump(exclude_unset=True, mode="json"),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await notification_service.notify_admins(
        type="app_master_edit",
        title="App Master row edited",
        body=f"{context.email} edited {key}: {', '.join(changes) or '—'}",
        actor_id=context.user_id,
        resource=key,
    )
    return updated


@router.post("/refresh", response_model=dict)
async def refresh_app_master(
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> dict[str, int]:
    """Re-pull the whole table from BigQuery into the Postgres serving copy (admin-only)."""
    try:
        result = await app_master_service.refresh_from_bigquery(db, get_settings())
    except (BigQueryNotConfigured, BigQueryUnavailable) as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "BigQuery is not configured — the serving copy was not refreshed.",
        ) from exc
    except BigQueryReadError as exc:
        await db.rollback()
        # Surface the sanitized reason (e.g. NotFound / Forbidden / BadRequest) so the admin
        # can tell whether it's the table name, columns, or permissions — not a blank 500.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    await audit.log_admin_action(
        user_id=context.user_id,
        action="admin_refresh_app_master",
        resource="app_master",
        detail=result,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await notification_service.notify_admins(
        type="app_master_refresh",
        title="App Master refreshed from BigQuery",
        body=f"Synced {result.get('synced', 0)} apps"
        + (f" · skipped {result['skipped']}" if result.get("skipped") else ""),
        actor_id=context.user_id,
        resource="app_master",
    )
    return result

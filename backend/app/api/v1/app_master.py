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
from app.schemas.app_master import AppMasterListResponse, AppMasterUpdate
from app.schemas.integration import SchemaDiff
from app.services import app_master_service
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
    platform: str | None = None,
    hou: str | None = None,
    pod: int | None = None,
    needs_review: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AppMasterListResponse:
    """List rows with the App Master page's own filters (search/platform/hou/pod/review)."""
    return await app_master_service.list_rows(
        db,
        search=search,
        platform=platform,
        hou=hou,
        pod=pod,
        needs_review=needs_review,
        limit=limit,
        offset=offset,
    )


@router.get("/schema-diff", response_model=SchemaDiff)
async def app_master_schema_diff(context: CurrentUser, db: DbSession) -> SchemaDiff:
    """Read-only check that the configured BigQuery table's columns match the registry."""
    return await app_master_service.schema_diff(db, get_settings())


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
        updated = await app_master_service.update_row(db, get_settings(), key, changes)
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
    return result

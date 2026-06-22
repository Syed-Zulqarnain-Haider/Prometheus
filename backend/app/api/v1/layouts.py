"""Per-user dashboard layout persistence (drag-and-drop Phase 2).

Each user reads and writes ONLY their own layout — every query is scoped to
``context.user_id``, so one user's arrangement can never read or overwrite
another's. Saves and resets are audited. When a user has no saved layout the
endpoint returns ``layout=None`` and the client falls back to its default.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import CurrentUser, DbSession
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models import DashboardLayout
from app.schemas.layouts import DashboardLayoutOut, DashboardLayoutSave
from app.services.audit import AuditDep

router = APIRouter(
    prefix="/dashboard-layouts",
    tags=["dashboard-layouts"],
    dependencies=[Depends(enforce_rate_limit)],
)

# Pages that support a customizable layout. Validated so the table can't be
# filled with arbitrary page keys.
ALLOWED_PAGES = frozenset({"overview"})


def _validate_page(page: str) -> None:
    if page not in ALLOWED_PAGES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown layout page")


@router.get("/{page}", response_model=DashboardLayoutOut)
async def get_layout(page: str, context: CurrentUser, db: DbSession) -> DashboardLayoutOut:
    """Load THIS user's saved layout for the page (or layout=None if none saved)."""
    _validate_page(page)
    row = await db.scalar(
        select(DashboardLayout).where(
            DashboardLayout.user_id == context.user_id, DashboardLayout.page == page
        )
    )
    if row is None:
        return DashboardLayoutOut(page=page, layout=None, updated_at=None)
    return DashboardLayoutOut(page=page, layout=row.layout, updated_at=row.updated_at)


@router.put("/{page}", response_model=DashboardLayoutOut)
async def save_layout(
    page: str,
    body: DashboardLayoutSave,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> DashboardLayoutOut:
    """Save (upsert) THIS user's layout for the page."""
    _validate_page(page)
    now = datetime.now(UTC)
    # Upsert scoped to the caller — the PK (user_id, page) guarantees one row per
    # user/page and the conflict target makes a re-save idempotent.
    stmt = (
        pg_insert(DashboardLayout)
        .values(user_id=context.user_id, page=page, layout=body.layout, updated_at=now)
        .on_conflict_do_update(
            index_elements=[DashboardLayout.user_id, DashboardLayout.page],
            set_={"layout": body.layout, "updated_at": now},
        )
    )
    await db.execute(stmt)
    await db.commit()

    await audit.write(
        user_id=context.user_id,
        action="dashboard_layout_save",
        resource=page,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return DashboardLayoutOut(page=page, layout=body.layout, updated_at=now)


@router.post("/{page}/reset", response_model=DashboardLayoutOut)
async def reset_layout(
    page: str,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> DashboardLayoutOut:
    """Clear THIS user's saved layout, restoring the default arrangement."""
    _validate_page(page)
    row = await db.scalar(
        select(DashboardLayout).where(
            DashboardLayout.user_id == context.user_id, DashboardLayout.page == page
        )
    )
    if row is not None:
        await db.delete(row)
        await db.commit()

    await audit.write(
        user_id=context.user_id,
        action="dashboard_layout_reset",
        resource=page,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return DashboardLayoutOut(page=page, layout=None, updated_at=None)

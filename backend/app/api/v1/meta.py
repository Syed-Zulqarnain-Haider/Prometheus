"""Meta routes: data freshness from sync_runs (the 'data as of' banner)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import enforce_rate_limit
from app.models import SyncRun
from app.schemas.admin import TargetsResponse
from app.services import admin_service

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(enforce_rate_limit)])


@router.get("/freshness")
async def freshness(context: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Latest run status plus the last successfully-built BigQuery timestamp."""
    latest = (
        (await db.execute(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))).scalars().first()
    )
    last_success = (
        (
            await db.execute(
                select(SyncRun)
                .where(SyncRun.status == "success")
                .order_by(SyncRun.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    return {
        "bq_built_at": last_success.bq_built_at.isoformat()
        if last_success and last_success.bq_built_at
        else None,
        "last_status": latest.status if latest else None,
        "last_run_finished_at": latest.finished_at.isoformat()
        if latest and latest.finished_at
        else None,
        "rows_loaded": last_success.rows_loaded if last_success else None,
    }


@router.get("/targets", response_model=TargetsResponse)
async def targets(
    context: CurrentUser, db: DbSession, year: int = Query(ge=2000, le=2100)
) -> TargetsResponse:
    """Revenue targets for a year (read-only) — powers the Overview progress donut.

    Visible to any authenticated user; only admins can set them (``/admin/targets``).
    """
    annual, monthly = await admin_service.targets_for_year(db, year)
    return TargetsResponse(year=year, annual=annual, monthly=monthly)

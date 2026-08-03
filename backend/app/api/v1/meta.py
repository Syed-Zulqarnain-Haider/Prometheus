"""Meta routes: data freshness from sync_runs (the 'data as of' banner)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.api.v1.metrics import get_filters
from app.core.cache import aggregate_cache_key, cached_json, scope_token
from app.core.rate_limit import enforce_rate_limit
from app.models import SyncRun
from app.schemas.admin import TargetsResponse
from app.schemas.metrics import AppOption, FilterOptions, MetricFilters
from app.schemas.system import ClientSettings
from app.services import admin_service, settings_service
from app.services.query_builder import QueryBuilder

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(enforce_rate_limit)])

# (column on the fact table, the filter key to clear when computing its own options)
_OPTION_DIMS: list[tuple[str, str, str]] = [
    ("platforms", "platform", "platform"),
    ("consoles", "rpt_console", "consoles"),
    ("pod_owners", "pod_owner", "pod_owners"),
    ("publishers", "publisher", "publishers"),
    ("developers", "developer", "developers"),
    ("google_play_accounts", "google_play_account", "google_play_accounts"),
    ("apple_accounts", "apple_account", "apple_accounts"),
    ("packages", "android_package", "packages"),
    ("bundles", "ios_bundle_id", "bundles"),
    ("hous", "hou", "hou"),
]


@router.get("/filter-options", response_model=FilterOptions)
async def filter_options(
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    filters: Annotated[MetricFilters, Depends(get_filters)],
) -> FilterOptions:
    """Cascading options for every filter dropdown — each dimension's values reflect the
    other active filters + the caller's scope + the date window. Fixes 'platform=iOS still
    lists non-iOS HOUs': each list is computed with its OWN selection cleared.

    Cached (agg:*, TTL-aligned to the daily rebuild) like the other aggregate endpoints — the
    frontend refetches this on every filter change, and it is otherwise 11 GROUP BY/DISTINCT
    scans per request. The key varies by scope + filters; it is dimension-only, so no perms
    token is needed."""
    qb = QueryBuilder(context)
    key = aggregate_cache_key(
        "meta.filter-options", scope_token(context.scopes), "", filters.model_dump(mode="json")
    )

    async def produce() -> dict[str, Any]:
        result = FilterOptions()
        for field, column, self_key in _OPTION_DIMS:
            rows = (await db.execute(qb.distinct_values(filters, column, self_key))).all()
            setattr(result, field, [r.value for r in rows if r.value is not None])
        app_rows = (
            await db.execute(
                qb.distinct_values(filters, "canonical_key", "apps", label="app_name")
            )
        ).all()
        result.apps = [
            AppOption(value=r.value, label=r.label) for r in app_rows if r.value is not None
        ]
        return result.model_dump(mode="json")

    data: dict[str, Any] = await cached_json(redis, key, produce)
    return FilterOptions.model_validate(data)


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


@router.get("/settings", response_model=ClientSettings)
async def client_settings(context: CurrentUser, db: DbSession) -> ClientSettings:
    """Operational settings the UI reacts to (e.g. demo-widget toggle, freshness
    threshold). Non-secret; readable by any authenticated user."""
    return await settings_service.client_settings(db)


@router.get("/targets", response_model=TargetsResponse)
async def targets(
    context: CurrentUser, db: DbSession, year: int = Query(ge=2000, le=2100)
) -> TargetsResponse:
    """Revenue targets for a year (read-only) — powers the Overview progress donut.

    Visible to any authenticated user; only admins can set them (``/admin/targets``).
    """
    annual, monthly = await admin_service.targets_for_year(db, year)
    return TargetsResponse(year=year, annual=annual, monthly=monthly)

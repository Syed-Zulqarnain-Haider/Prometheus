"""Idempotent warm-up of the aggregate cache for the Overview's default view.

Pre-populates ``agg:*`` entries for the most common dashboard request — the default
30-day Executive Overview for a full-visibility (all metric groups), all-scope
caller — so the first real visit after a deploy or the daily cache bust hits warm
cache instead of paying the cold Neon recompute. Each job mirrors a real Overview
request exactly (same route + params), so warmed entries are read by real requests.

Best-effort and non-fatal: any failure is logged and skipped (the endpoint simply
recomputes on demand). Warming the all-groups/all-scope profile can never serve data
to a lower-privilege caller — the cache key varies by scope AND permitted groups.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache import aggregate_cache_key, cached_json, perms_token, scope_token
from app.schemas.auth import ScopeOut, UserContext
from app.schemas.metrics import MetricFilters
from app.services import metrics_service
from app.services.query_builder import QueryBuilder

log = logging.getLogger("app.cache_warm")

# The full-visibility, all-scope profile shared by admin / executive / pod_owner —
# the most common Overview audience.
_ALL_GROUPS = [
    "store_installs",
    "ua_spend",
    "ad_revenue",
    "iap_revenue",
    "attribution",
    "profitability",
]
_DEFAULT_RANGE_DAYS = 30  # matches the frontend default "30D" preset
_SPARK_METRICS = [
    "total_revenue_usd",
    "total_ua_spend_usd",
    "total_iap_gross_usd",
    "total_ad_revenue_usd",
    "tech_cost_usd",
]


def _warm_context() -> UserContext:
    return UserContext(
        user_id=uuid.UUID(int=0),
        firebase_uid="__cache_warmer__",
        email="cache-warmer@internal",
        display_name=None,
        is_active=True,
        roles=[],
        metric_groups=list(_ALL_GROUPS),
        capabilities=[],
        scopes=[ScopeOut(scope_type="all", scope_value=None)],
    )


def _default_filters() -> MetricFilters:
    today = datetime.now(UTC).date()
    return MetricFilters(
        date_from=today - timedelta(days=_DEFAULT_RANGE_DAYS - 1),
        date_to=today,
    )


def _params(filters: MetricFilters, **extra: Any) -> dict[str, Any]:
    # Mirrors metrics.py::_params so warmed keys match real request keys exactly.
    return {**filters.model_dump(mode="json"), **extra}


async def warm_overview_cache(sessionmaker: async_sessionmaker[AsyncSession], redis: Redis) -> int:
    """Populate the default-Overview aggregate entries. Returns the count warmed."""
    ctx = _warm_context()
    scope = scope_token(ctx.scopes)
    perms = perms_token(ctx.metric_groups)
    f = _default_filters()
    warmed = 0

    async with sessionmaker() as db:
        qb = QueryBuilder(ctx)

        async def run(
            route: str,
            params: dict[str, Any],
            producer: Callable[[], Awaitable[Any]],
        ) -> None:
            nonlocal warmed
            key = aggregate_cache_key(route, scope, perms, params)
            try:
                await cached_json(redis, key, producer)
                warmed += 1
            except Exception:  # noqa: BLE001 — warming is best-effort, never fatal
                log.exception("cache warm failed for %s", route)

        # Each entry below mirrors a default Overview request (30-day range, no extra
        # filters). Metric lists are sorted to match the endpoints' cache keys; the
        # producers (functools.partial) bind their args eagerly — no loop-var capture.
        await run("metrics.summary", _params(f), partial(metrics_service.run_summary, db, qb, f))
        await run(
            "metrics.timeseries",
            _params(f, metrics=sorted(_SPARK_METRICS), bucket="day"),
            partial(metrics_service.run_timeseries, db, qb, f, _SPARK_METRICS, "day"),
        )
        await run(
            "metrics.timeseries",
            _params(f, metrics=["total_revenue_usd"], bucket="month"),
            partial(metrics_service.run_timeseries, db, qb, f, ["total_revenue_usd"], "month"),
        )
        day_series = (
            ["total_iap_net_usd", "total_ad_revenue_usd"],  # revenue composition
            ["total_revenue_usd", "total_ua_spend_usd"],  # revenue vs spend
        )
        for metrics in day_series:
            await run(
                "metrics.timeseries",
                _params(f, metrics=sorted(metrics), bucket="day"),
                partial(metrics_service.run_timeseries, db, qb, f, metrics, "day"),
            )
        for group_by in ("platform", "pod"):
            await run(
                "metrics.breakdown",
                _params(f, group_by=group_by, metrics=["total_revenue_usd"], limit=100),
                partial(
                    metrics_service.run_breakdown, db, qb, f, group_by, ["total_revenue_usd"], 100
                ),
            )
        await run(
            "metrics.table",
            _params(f, sort="total_revenue_usd", direction="desc", limit=100, cursor=None),
            partial(
                metrics_service.run_table,
                db,
                qb,
                f,
                sort="total_revenue_usd",
                direction="desc",
                limit=100,
                cursor=None,
            ),
        )

    log.info("aggregate cache warm-up complete: %d entries", warmed)
    return warmed

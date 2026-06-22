"""Metrics routes: summary, timeseries, breakdown, table.

All are GET, authenticated, rate-limited, and cached (agg:*, TTL aligned to the daily
rebuild). RBAC column filtering is inherent — the query builder only aggregates the
caller's permitted measures, and period ratios only appear when their components are
permitted; the cache key also varies by scope + permitted groups so payloads are never
shared across permission profiles.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.cache import aggregate_cache_key, cached_json, perms_token, scope_token
from app.core.rate_limit import enforce_rate_limit
from app.schemas.metrics import Bucket, GroupBy, MetricFilters, Platform, SortDirection
from app.services import metrics_service
from app.services.metrics_service import decode_cursor
from app.services.query_builder import QueryBuilder

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(enforce_rate_limit)])


def get_filters(
    date_from: date,
    date_to: date,
    compare: bool = False,
    platform: Platform | None = None,
    pods: Annotated[list[str] | None, Query()] = None,
    publishers: Annotated[list[str] | None, Query()] = None,
    apps: Annotated[list[str] | None, Query()] = None,
) -> MetricFilters:
    try:
        return MetricFilters(
            date_from=date_from,
            date_to=date_to,
            compare=compare,
            platform=platform,
            pods=pods or [],
            publishers=publishers or [],
            apps=apps or [],
        )
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "date_from must be on or before date_to"
        ) from exc


Filters = Annotated[MetricFilters, Depends(get_filters)]


def _params(filters: MetricFilters, **extra: Any) -> dict[str, Any]:
    return {**filters.model_dump(mode="json"), **extra}


@router.get("/summary")
async def summary(
    filters: Filters, context: CurrentUser, db: DbSession, redis: RedisClient
) -> dict[str, Any]:
    qb = QueryBuilder(context)
    key = aggregate_cache_key(
        "metrics.summary",
        scope_token(context.scopes),
        perms_token(context.metric_groups),
        _params(filters),
    )

    async def produce() -> dict[str, Any]:
        return await metrics_service.run_summary(db, qb, filters)

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return result


@router.get("/timeseries")
async def timeseries(
    filters: Filters,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    metrics: Annotated[list[str], Query(min_length=1)],
    bucket: Bucket = "day",
) -> dict[str, Any]:
    qb = QueryBuilder(context)
    key = aggregate_cache_key(
        "metrics.timeseries",
        scope_token(context.scopes),
        perms_token(context.metric_groups),
        _params(filters, metrics=sorted(metrics), bucket=bucket),
    )

    async def produce() -> dict[str, Any]:
        try:
            return await metrics_service.run_timeseries(db, qb, filters, metrics, bucket)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return result


@router.get("/breakdown")
async def breakdown(
    filters: Filters,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    group_by: GroupBy,
    metrics: Annotated[list[str], Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    qb = QueryBuilder(context)
    key = aggregate_cache_key(
        "metrics.breakdown",
        scope_token(context.scopes),
        perms_token(context.metric_groups),
        _params(filters, group_by=group_by, metrics=sorted(metrics), limit=limit),
    )

    async def produce() -> dict[str, Any]:
        try:
            return await metrics_service.run_breakdown(db, qb, filters, group_by, metrics, limit)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return result


@router.get("/table")
async def table(
    filters: Filters,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    sort: str,
    direction: SortDirection = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    qb = QueryBuilder(context)
    try:
        cursor_tuple = decode_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    key = aggregate_cache_key(
        "metrics.table",
        scope_token(context.scopes),
        perms_token(context.metric_groups),
        _params(filters, sort=sort, direction=direction, limit=limit, cursor=cursor),
    )

    async def produce() -> dict[str, Any]:
        try:
            return await metrics_service.run_table(
                db,
                qb,
                filters,
                sort=sort,
                direction=direction,
                limit=limit,
                cursor=cursor_tuple,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return result

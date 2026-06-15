"""Executes query-builder statements and shapes JSON-safe response payloads.

Also recomputes period-level ratio KPIs from aggregated totals (summary) and
encodes/decodes keyset pagination cursors (table).
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics import Bucket, GroupBy, MetricFilters, SortDirection
from app.services.period_ratios import compute_period_differences, compute_period_ratios
from app.services.query_builder import QueryBuilder

_PREVIOUS_SUFFIX = "__previous"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _row_dict(mapping: Any) -> dict[str, Any]:
    return {key: _to_jsonable(value) for key, value in mapping.items()}


def encode_cursor(sort_value: Any, key: str) -> str:
    raw = json.dumps([_to_jsonable(sort_value), key])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(token: str) -> tuple[Any, str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        value, key = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid cursor") from exc
    return value, str(key)


async def run_summary(
    session: AsyncSession, qb: QueryBuilder, params: MetricFilters
) -> dict[str, Any]:
    row = (await session.execute(qb.summary(params))).mappings().one()
    current_raw: dict[str, Any] = {}
    previous_raw: dict[str, Any] = {}
    for key, value in row.items():
        if key.endswith(_PREVIOUS_SUFFIX):
            previous_raw[key[: -len(_PREVIOUS_SUFFIX)]] = value
        else:
            current_raw[key] = value

    result: dict[str, Any] = {
        "current": {
            **{k: _to_jsonable(v) for k, v in current_raw.items()},
            **compute_period_ratios(current_raw),
            **compute_period_differences(current_raw),
        },
        "previous": None,
    }
    if params.compare:
        result["previous"] = {
            **{k: _to_jsonable(v) for k, v in previous_raw.items()},
            **compute_period_ratios(previous_raw),
            **compute_period_differences(previous_raw),
        }
    return result


async def run_timeseries(
    session: AsyncSession,
    qb: QueryBuilder,
    params: MetricFilters,
    metrics: list[str],
    bucket: Bucket,
) -> dict[str, Any]:
    rows = (await session.execute(qb.timeseries(params, metrics, bucket))).mappings().all()
    return {"bucket": bucket, "metrics": metrics, "series": [_row_dict(r) for r in rows]}


async def run_breakdown(
    session: AsyncSession,
    qb: QueryBuilder,
    params: MetricFilters,
    group_by: GroupBy,
    metrics: list[str],
    limit: int,
) -> dict[str, Any]:
    rows = (
        (await session.execute(qb.breakdown(params, group_by, metrics, limit=limit)))
        .mappings()
        .all()
    )
    return {"group_by": group_by, "rows": [_row_dict(r) for r in rows]}


async def run_table(
    session: AsyncSession,
    qb: QueryBuilder,
    params: MetricFilters,
    *,
    sort: str,
    direction: SortDirection,
    limit: int,
    cursor: tuple[Any, str] | None,
) -> dict[str, Any]:
    stmt = qb.table(params, sort=sort, direction=direction, limit=limit, cursor=cursor)
    rows = (await session.execute(stmt)).mappings().all()
    data = [_row_dict(r) for r in rows]
    next_cursor: str | None = None
    if len(rows) == limit and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last[sort], last["canonical_key"])
    return {"rows": data, "next_cursor": next_cursor}

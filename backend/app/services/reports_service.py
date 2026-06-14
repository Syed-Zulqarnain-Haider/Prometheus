"""Report execution + export building, all under the runner's own RBAC.

A report is "group by <dimension>, show <metric columns> over <filters>". Running
or exporting it always re-derives the rows server-side through the *caller's*
QueryBuilder (scope + permitted metrics), so a shared report can never expose data
the recipient couldn't otherwise see.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics import MetricFilters
from app.services.metrics_service import _row_dict
from app.services.query_builder import QueryBuilder


def metric_filters_from_dict(filters: dict[str, Any]) -> MetricFilters:
    """Build MetricFilters from a stored report's filter JSON (API-query shape)."""
    try:
        return MetricFilters(
            date_from=filters["date_from"],
            date_to=filters["date_to"],
            platform=filters.get("platform"),
            pods=filters.get("pods") or [],
            publishers=filters.get("publishers") or [],
            apps=filters.get("apps") or [],
        )
    except (KeyError, ValidationError, ValueError) as exc:
        raise ValueError("report filters must include a valid date_from/date_to") from exc


def validate_columns(columns: list[str], permitted: set[str]) -> None:
    """On write: every column must be a metric the author is permitted to aggregate."""
    forbidden = [c for c in columns if c not in permitted]
    if forbidden:
        raise ValueError(f"columns not permitted or not additive: {forbidden}")


async def run_report(
    session: AsyncSession,
    qb: QueryBuilder,
    filters: MetricFilters,
    group_by: str,
    columns: list[str],
) -> dict[str, Any]:
    """Execute the report under ``qb``'s RBAC, dropping any columns the runner
    isn't permitted to see (so recipients only ever get their own subset)."""
    cols = [c for c in columns if c in qb.permitted_measures]
    if not cols:
        return {"group_by": group_by, "columns": [], "rows": []}

    if group_by == "date":
        stmt = qb.timeseries(filters, cols, "day")
    else:
        stmt = qb.breakdown(filters, group_by, cols)  # type: ignore[arg-type]

    rows = (await session.execute(stmt)).mappings().all()
    return {"group_by": group_by, "columns": cols, "rows": [_row_dict(r) for r in rows]}


def _ordered_fields(result: dict[str, Any]) -> list[str]:
    rows = result["rows"]
    if not rows:
        # Header from the known shape even when empty.
        label = "bucket" if result["group_by"] == "date" else result["group_by"]
        return [label, *result["columns"]]
    return list(rows[0].keys())


def build_csv(result: dict[str, Any]) -> bytes:
    fields = _ordered_fields(result)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in result["rows"]:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def build_xlsx(result: dict[str, Any]) -> bytes:
    from openpyxl import Workbook

    fields = _ordered_fields(result)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Report"
    sheet.append(fields)
    for row in result["rows"]:
        sheet.append([row.get(f) for f in fields])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()

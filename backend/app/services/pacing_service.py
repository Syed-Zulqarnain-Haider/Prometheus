"""Budget pacing: month-to-date revenue vs the admin-set target, with a linear projection.

Everything is computed under the CALLER's RBAC (their scoped revenue via QueryBuilder), so a
scoped user sees pacing for THEIR slice; the target is the org's month goal. When the caller
isn't permitted to see revenue, actual/projection come back null (target-only).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RevenueTarget
from app.schemas.metrics import MetricFilters
from app.services import metrics_service
from app.services.query_builder import QueryBuilder

_REVENUE = "total_revenue_usd"


@dataclass
class Pacing:
    year: int
    month: int
    target_usd: float | None
    actual_usd: float | None
    days_elapsed: int
    days_in_month: int
    expected_to_date_usd: float | None
    projected_usd: float | None
    attainment_pct: float | None  # actual / target
    pace_pct: float | None  # actual / expected_to_date (>1 ahead of pace)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


async def _month_target(db: AsyncSession, year: int, month: int) -> float | None:
    row = await db.scalar(
        select(RevenueTarget.target_usd).where(
            and_(
                RevenueTarget.period_type == "month",
                RevenueTarget.period_year == year,
                RevenueTarget.period_month == month,
            )
        )
    )
    return float(row) if row is not None else None


async def compute(
    db: AsyncSession, context: Any, year: int, month: int, today: date
) -> dict[str, Any]:
    """Pacing for ``year``-``month`` as of ``today``."""
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    # Days elapsed within the month (0 if the month is entirely in the future; full month if
    # entirely in the past).
    if today < month_start:
        days_elapsed = 0
    elif today >= month_end:
        days_elapsed = days_in_month
    else:
        days_elapsed = (today - month_start).days + 1

    qb = QueryBuilder(context)
    # The target is a revenue figure — only disclose it to callers permitted a revenue measure,
    # so a store-installs-only role never learns the org's revenue goal (parity with how
    # forbidden metrics are never serialized elsewhere).
    can_see_revenue = _REVENUE in qb.permitted_measures
    target = await _month_target(db, year, month) if can_see_revenue else None

    actual: float | None = None
    if can_see_revenue and days_elapsed > 0:
        window_end = min(today, month_end)
        filters = MetricFilters(date_from=month_start, date_to=window_end)
        summary = await metrics_service.run_summary(db, qb, filters)
        actual = float(summary["current"].get(_REVENUE) or 0.0)

    fraction = days_elapsed / days_in_month if days_in_month else 0.0
    expected = target * fraction if (target is not None and fraction > 0) else None
    projected = (actual / fraction) if (actual is not None and fraction > 0) else None
    attainment = (actual / target) if (actual is not None and target) else None
    pace = (actual / expected) if (actual is not None and expected) else None

    return Pacing(
        year=year,
        month=month,
        target_usd=target,
        actual_usd=actual,
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
        expected_to_date_usd=expected,
        projected_usd=projected,
        attainment_pct=attainment,
        pace_pct=pace,
    ).as_dict()

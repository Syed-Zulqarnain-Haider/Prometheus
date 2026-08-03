"""Lightweight time-series forecasting for a single metric.

A deliberately simple, explainable model: an ordinary-least-squares linear trend fit over the
caller's SCOPED daily history (via QueryBuilder), projected forward N days and floored at 0.
No heavy dependency, no hidden magic — it's a straight-line trend, labelled as such, so nobody
mistakes it for a guarantee. Runs entirely under the caller's RBAC, like every other metric.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics import MetricFilters
from app.services import metrics_service
from app.services.query_builder import QueryBuilder

MAX_HORIZON = 90


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Return (slope, intercept) of the OLS line y = intercept + slope*x for given xs, ys."""
    n = len(ys)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:  # a single point (or all-equal x) → flat line at the mean
        return 0.0, mean_y
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = cov / var_x
    return slope, mean_y - slope * mean_x


async def forecast(
    db: AsyncSession,
    context: Any,
    filters: MetricFilters,
    metric: str,
    horizon: int,
) -> dict[str, Any]:
    """History (daily) for ``metric`` plus a linear projection ``horizon`` days past the last
    data day.

    The trend is fit over CALENDAR-DAY offsets, not row indices — the daily series only contains
    days that have rows (Apple lag, sparse scoped apps), so treating gaps as contiguous would
    distort the slope. Fitting on real day offsets keeps the trend honest. Raises ValueError if
    the metric isn't permitted/additive (surfaced as a 400 upstream)."""
    horizon = max(1, min(MAX_HORIZON, horizon))
    qb = QueryBuilder(context)  # validates the metric against permitted measures
    ts = await metrics_service.run_timeseries(db, qb, filters, [metric], "day")

    # Parse buckets defensively — skip anything non-ISO instead of crashing the request.
    points: list[tuple[date, float]] = []
    for row in ts["series"]:
        try:
            day = date.fromisoformat(str(row["bucket"])[:10])
        except (KeyError, ValueError):
            continue
        points.append((day, float(row.get(metric) or 0.0)))

    history: list[dict[str, Any]] = [{"date": d.isoformat(), "value": v} for d, v in points]
    if len(points) < 2:
        # Not enough signal to fit a trend — return history with an empty forecast.
        return {"metric": metric, "method": "linear", "history": history, "forecast": []}

    first_day = points[0][0]
    xs = [float((d - first_day).days) for d, _ in points]
    ys = [v for _, v in points]
    slope, intercept = _linear_fit(xs, ys)

    last_day, last_x = points[-1][0], xs[-1]
    projection = [
        {
            "date": (last_day + timedelta(days=step)).isoformat(),
            "value": max(0.0, round(intercept + slope * (last_x + step), 4)),
        }
        for step in range(1, horizon + 1)
    ]
    return {"metric": metric, "method": "linear", "history": history, "forecast": projection}

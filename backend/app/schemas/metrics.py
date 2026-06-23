"""Validated request schemas for the metrics query layer."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, model_validator

Bucket = Literal["day", "week", "month"]
GroupBy = Literal["app", "pod", "publisher", "platform", "hou"]
SortDirection = Literal["asc", "desc"]
Platform = Literal["ios", "android"]

# Server-side guards against query-amplification abuse (RT-M1). Generous enough that
# the dashboard's own queries (default 30D, max 90D preset; a handful of filter
# values) are unaffected, but they bound a hostile request's cost.
MAX_RANGE_DAYS = 400
MAX_FILTER_VALUES = 100


class MetricFilters(BaseModel):
    """Common, already-validated filter parameters for every metrics query.

    The scope filter (from the caller's token) is applied independently and ALWAYS
    first; these client filters can only narrow the result, never widen it.
    """

    date_from: date
    date_to: date
    compare: bool = False
    platform: Platform | None = None
    pods: list[str] = []
    publishers: list[str] = []
    apps: list[str] = []

    @model_validator(mode="after")
    def _validate_bounds(self) -> MetricFilters:
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        span_days = (self.date_to - self.date_from).days + 1  # inclusive
        if span_days > MAX_RANGE_DAYS:
            raise ValueError(f"date range too large: {span_days} days (max {MAX_RANGE_DAYS})")
        dimensions = (("pods", self.pods), ("publishers", self.publishers), ("apps", self.apps))
        for name, values in dimensions:
            if len(values) > MAX_FILTER_VALUES:
                raise ValueError(
                    f"too many {name} filter values: {len(values)} (max {MAX_FILTER_VALUES})"
                )
        return self

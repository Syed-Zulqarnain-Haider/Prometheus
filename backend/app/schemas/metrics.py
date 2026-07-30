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
# Generous enough for the "All time" preset (data starts ~2020) yet still an amplification
# guard against absurd multi-decade spans. Aggregates use the date covering index.
MAX_RANGE_DAYS = 4200
MAX_FILTER_VALUES = 100


class AppOption(BaseModel):
    value: str
    label: str | None = None


class FilterOptions(BaseModel):
    """Cascading filter-bar options: each list holds the values available for that dimension
    GIVEN the other active filters (so the dropdowns narrow each other, e.g. platform=ios →
    only iOS HOUs). Scoped to the caller's RBAC row access and the selected date window."""

    platforms: list[str] = []
    consoles: list[str] = []
    pod_owners: list[str] = []
    publishers: list[str] = []
    developers: list[str] = []
    google_play_accounts: list[str] = []
    apple_accounts: list[str] = []
    packages: list[str] = []
    bundles: list[str] = []
    hous: list[str] = []
    apps: list[AppOption] = []


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
    hou: list[str] = []
    # Additional narrowing dimensions (Console + account/dev/package/bundle filters).
    pod_owners: list[str] = []
    consoles: list[str] = []
    developers: list[str] = []
    google_play_accounts: list[str] = []
    apple_accounts: list[str] = []
    packages: list[str] = []  # android_package
    bundles: list[str] = []  # ios_bundle_id

    @model_validator(mode="after")
    def _validate_bounds(self) -> MetricFilters:
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        span_days = (self.date_to - self.date_from).days + 1  # inclusive
        if span_days > MAX_RANGE_DAYS:
            raise ValueError(f"date range too large: {span_days} days (max {MAX_RANGE_DAYS})")
        dimensions = (
            ("pods", self.pods),
            ("publishers", self.publishers),
            ("apps", self.apps),
            ("hou", self.hou),
            ("pod_owners", self.pod_owners),
            ("consoles", self.consoles),
            ("developers", self.developers),
            ("google_play_accounts", self.google_play_accounts),
            ("apple_accounts", self.apple_accounts),
            ("packages", self.packages),
            ("bundles", self.bundles),
        )
        for name, values in dimensions:
            if len(values) > MAX_FILTER_VALUES:
                raise ValueError(
                    f"too many {name} filter values: {len(values)} (max {MAX_FILTER_VALUES})"
                )
        return self

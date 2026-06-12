"""Validated request schemas for the metrics query layer."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, model_validator

Bucket = Literal["day", "week", "month"]
GroupBy = Literal["app", "pod", "publisher", "platform", "hou"]
SortDirection = Literal["asc", "desc"]
Platform = Literal["ios", "android"]


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
    def _validate_dates(self) -> MetricFilters:
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self

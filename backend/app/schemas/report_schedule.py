"""Schemas for scheduled report delivery."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

Cadence = Literal["daily", "weekly", "monthly"]
ReportFormat = Literal["csv", "xlsx"]


class ReportScheduleCreate(BaseModel):
    cadence: Cadence
    hour: int = Field(ge=0, le=23)
    # Required per cadence (validated below): weekly → day_of_week (0=Mon..6=Sun),
    # monthly → day_of_month (1-28, capped so every month has the day).
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    fmt: ReportFormat = "xlsx"
    timezone: str = "UTC"
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self) -> ReportScheduleCreate:
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:  # noqa: BLE001 — any failure means "not a valid tz"
            raise ValueError("timezone must be a valid IANA timezone (e.g. UTC)") from exc
        if self.cadence == "weekly" and self.day_of_week is None:
            raise ValueError("weekly schedules require day_of_week (0=Mon .. 6=Sun)")
        if self.cadence == "monthly" and self.day_of_month is None:
            raise ValueError("monthly schedules require day_of_month (1-28)")
        return self


class ReportScheduleOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    cadence: Cadence
    hour: int
    day_of_week: int | None
    day_of_month: int | None
    fmt: ReportFormat
    timezone: str
    enabled: bool
    last_run_on: date | None
    created_at: datetime

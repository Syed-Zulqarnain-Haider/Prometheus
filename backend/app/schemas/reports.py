"""Schemas for saved views, saved reports, sharing, and exports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# group_by allowed for reports (mirrors saved_reports.group_by CHECK).
ReportGroupBy = Literal["app", "pod", "publisher", "platform", "hou", "date"]
ExportFormat = Literal["csv", "xlsx", "gsheet"]


# ── Saved views ──────────────────────────────────────────────────────────────
class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    page: str = Field(min_length=1, max_length=80)
    filters: dict[str, Any]


class SavedViewOut(BaseModel):
    id: uuid.UUID
    name: str
    page: str
    filters: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ── Saved reports ────────────────────────────────────────────────────────────
class SavedReportCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    filters: dict[str, Any]
    columns: list[str] = Field(min_length=1)
    group_by: ReportGroupBy
    sort: dict[str, Any] | None = None


class SavedReportOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    filters: dict[str, Any]
    columns: list[str]
    group_by: str
    sort: dict[str, Any] | None
    owner_id: uuid.UUID
    is_owner: bool
    created_at: datetime
    updated_at: datetime


class ReportRunResult(BaseModel):
    group_by: str
    columns: list[str]
    rows: list[dict[str, Any]]


# ── Sharing ──────────────────────────────────────────────────────────────────
class ShareCreate(BaseModel):
    shared_with: uuid.UUID


class ShareOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    report_name: str | None = None
    shared_by: uuid.UUID
    shared_with: uuid.UUID
    status: str
    created_at: datetime


# ── Exports ──────────────────────────────────────────────────────────────────
class ExportRequest(BaseModel):
    format: ExportFormat
    # Either export a saved report by id, or an ad-hoc breakdown:
    report_id: uuid.UUID | None = None
    filters: dict[str, Any] | None = None
    columns: list[str] | None = None
    group_by: ReportGroupBy | None = None

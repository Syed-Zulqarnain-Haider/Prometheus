"""Schemas for the admin panel: users, role config, revenue targets, audit, health."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.auth import ScopeOut

ScopeType = Literal["all", "hou", "pod", "publisher", "app"]
MetricGroup = Literal[
    "store_installs", "ua_spend", "ad_revenue", "iap_revenue", "attribution", "profitability"
]
Capability = Literal["export", "share_report", "admin_panel"]
PeriodType = Literal["year", "month"]


# ── Users ─────────────────────────────────────────────────────────────────────
class ScopeIn(BaseModel):
    scope_type: ScopeType
    scope_value: str | None = None


class UserSummary(BaseModel):
    id: uuid.UUID
    firebase_uid: str
    email: str
    display_name: str | None
    is_active: bool
    roles: list[str]
    scopes: list[ScopeOut]
    created_at: datetime


class UserCreate(BaseModel):
    firebase_uid: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    scopes: list[ScopeIn] = Field(default_factory=list)


class UserUpdate(BaseModel):
    """Partial update. ``roles``/``scopes``, when present, REPLACE the existing set."""

    display_name: str | None = None
    is_active: bool | None = None
    roles: list[str] | None = None
    scopes: list[ScopeIn] | None = None


# ── Roles (metric-group permissions + capabilities) ──────────────────────────
class RoleConfig(BaseModel):
    id: int
    name: str
    metric_groups: list[str]
    capabilities: list[str]


class RoleUpdate(BaseModel):
    metric_groups: list[MetricGroup]
    capabilities: list[Capability]


# ── Revenue targets ───────────────────────────────────────────────────────────
class TargetOut(BaseModel):
    id: uuid.UUID
    period_type: str
    period_year: int
    period_month: int | None
    target_usd: float
    updated_at: datetime


class TargetUpsert(BaseModel):
    period_type: PeriodType
    period_year: int = Field(ge=2000, le=2100)
    period_month: int | None = Field(default=None, ge=1, le=12)
    target_usd: float = Field(ge=0)


class TargetsResponse(BaseModel):
    year: int
    annual: TargetOut | None
    monthly: list[TargetOut]


# ── Audit viewer ──────────────────────────────────────────────────────────────
class AuditEntry(BaseModel):
    id: int
    user_id: uuid.UUID | None
    user_email: str | None
    action: str
    resource: str | None
    detail: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditPage(BaseModel):
    entries: list[AuditEntry]
    next_offset: int | None


# ── Data health ───────────────────────────────────────────────────────────────
class SyncRunOut(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    rows_loaded: int | None
    rows_previous: int | None
    bq_built_at: datetime | None
    error_detail: str | None


class UnmappedApp(BaseModel):
    canonical_key: str
    app_name: str | None
    publisher: str | None
    platform_keys: str | None


class DataHealth(BaseModel):
    bq_built_at: datetime | None
    last_status: str | None
    last_run_finished_at: datetime | None
    rows_loaded: int | None
    is_stale: bool
    warnings: list[str]
    recent_runs: list[SyncRunOut]
    unmapped_count: int
    unmapped_apps: list[UnmappedApp]

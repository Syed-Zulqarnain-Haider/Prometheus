"""Schemas for the admin App Master page (Postgres copy of BigQuery app_master_v2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AppMasterColumnMeta(BaseModel):
    """Column metadata so the UI can render the grid generically + know what's editable."""

    name: str
    type: str  # text | bigint | boolean | double | timestamptz
    editable: bool


class AppMasterListResponse(BaseModel):
    """A page of rows plus the total (for the admin grid + pagination)."""

    rows: list[dict[str, Any]]
    total: int
    columns: list[AppMasterColumnMeta]
    primary_key: str


class AppMasterUpdate(BaseModel):
    """Partial update — ONLY the owner-approved editable columns. Unknown or read-only
    columns are rejected (``extra='forbid'``). Fields not provided are left unchanged;
    a field explicitly set to null clears it. Applied to BigQuery first, then Postgres."""

    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    publisher: str | None = None
    developer: str | None = None
    pod: int | None = None
    pod_owner: str | None = None
    hou: str | None = None
    app_type: str | None = None
    needs_review: bool | None = None
    review_reason: str | None = None
    revenue_share_pct: float | None = Field(default=None, ge=0)
    cost_share_pct: float | None = Field(default=None, ge=0)
    partner_name: str | None = None
    partnership_terms: str | None = None
    in_apple_console: bool | None = None
    in_gp_console: bool | None = None
    ops_notes: str | None = None
    third_party_os: str | None = None
    transsion_delightek: bool | None = None

"""Schemas for the admin App Master page (Postgres copy of BigQuery app_master_v2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.app_master_columns import EDITABLE_SET


class AppMasterColumnMeta(BaseModel):
    """Column metadata so the UI can render the grid generically + know what's editable."""

    name: str
    type: str  # text | bigint | boolean | double | timestamptz
    editable: bool


class AppMasterListResponse(BaseModel):
    """A page of rows plus the total (for the admin grid + pagination). ``columns`` is
    already ordered by the admin-set global ``column_order``."""

    rows: list[dict[str, Any]]
    total: int
    columns: list[AppMasterColumnMeta]
    column_order: list[str]
    primary_key: str


class AppMasterFilterValues(BaseModel):
    """Distinct values for the App Master filter dropdowns."""

    platforms: list[str]
    hou: list[str]
    publishers: list[str]
    pods: list[int]


class ColumnOrderUpdate(BaseModel):
    """Admin-set global column order (must be exactly the known columns, any order)."""

    order: list[str]


class AppMasterEditOut(BaseModel):
    """One entry in a row's change history (newest first)."""

    id: int
    canonical_key: str
    edited_at: Any
    editor_email: str | None
    action: str  # edit | undo
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    undone: bool


class AppMasterUpdate(BaseModel):
    """Partial update — ONLY the owner-approved editable columns (publisher, hou, pod_owner,
    pod, partner_name, net_revenue_share). Unknown or read-only columns are rejected
    (``extra='forbid'``). Fields not provided are left unchanged; a field explicitly set to
    null clears it. Applied to BigQuery first, then Postgres.

    These fields MUST stay in lockstep with ``app_master_columns.EDITABLE_SET`` — the
    module-level assert below fails the import if they ever drift."""

    model_config = ConfigDict(extra="forbid")

    publisher: str | None = None
    hou: str | None = None
    pod_owner: str | None = None
    pod: int | None = None
    partner_name: str | None = None
    net_revenue_share: float | None = None


# Drift guard: the editable API surface must equal the enforced editable set exactly.
assert set(AppMasterUpdate.model_fields) == EDITABLE_SET, (
    "AppMasterUpdate fields drifted from app_master_columns.EDITABLE_SET"
)

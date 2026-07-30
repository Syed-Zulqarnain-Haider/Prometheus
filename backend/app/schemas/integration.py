"""Schemas for the admin Integration tab: BigQuery → Postgres integration status and
the read-only BigQuery 'Test Connection' result.

Like the System schemas, these carry ONLY status + sanitized human notes — never a
connection string, key path, credential, or raw provider error.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.admin import SyncRunOut
from app.schemas.system import ConnectionStatus


class IntegrationStatus(BaseModel):
    """Composed Integration-tab status: connection health + recent sync history.

    ``bigquery`` reports whether the reader key is present at the configured path
    (presence only — the key is never read for this); ``postgres``/``redis`` are live
    pings. None of these fields ever contains a credential or connection string.
    """

    bigquery: ConnectionStatus
    postgres: ConnectionStatus
    redis: ConnectionStatus
    last_sync: SyncRunOut | None = None
    recent_syncs: list[SyncRunOut]


class BigQueryTestResult(BaseModel):
    """Result of the read-only BigQuery 'Test Connection' probe."""

    ok: bool
    message: str  # sanitized — never a credential, key path, or raw provider error


class SchemaColumnDiff(BaseModel):
    column: str
    expected: str
    actual: str


class BigQueryColumn(BaseModel):
    column: str
    data_type: str


class SchemaDiff(BaseModel):
    """Read-only, INFORMATIONAL diff of the live BigQuery view vs the metric registry.

    Adopting a new view column is always a DELIBERATE registry change — this never alters
    any schema, it only reports. ``in_sync`` is True when there are no missing (non-optional)
    columns and no type mismatches; optional-absent and unregistered columns are advisory.
    """

    configured: bool
    in_sync: bool = False
    message: str | None = None  # sanitized note (not-configured / library unavailable / error)
    missing_in_view: list[str] = []
    optional_absent: list[str] = []
    type_mismatches: list[SchemaColumnDiff] = []
    unregistered_in_view: list[BigQueryColumn] = []


class SchemaSyncColumn(BaseModel):
    """A column touched (or skipped) by a schema reconcile."""

    name: str
    type: str  # pg DDL type for added columns; BigQuery type for unsupported ones
    reason: str | None = None  # why it was skipped (unsupported_types only)


class SchemaSyncResult(BaseModel):
    """Result of the admin 'Match Database & BigQuery Schema' action.

    Additive + non-destructive: ``added`` columns were created in Postgres and are now
    served; ``deactivated`` columns vanished from BigQuery and are FLAGGED (kept, not
    dropped); ``missing_in_bigquery`` are static registry columns the source no longer
    exposes; ``unsupported_types`` are BigQuery columns skipped (unsafe name / unmapped
    type). ``ok`` is False only when BigQuery could not be read.
    """

    configured: bool
    ok: bool = False
    message: str | None = None  # sanitized note (not-configured / read failure)
    added: list[SchemaSyncColumn] = []
    reactivated: list[str] = []
    deactivated: list[str] = []
    healed_static: list[str] = []  # static columns that were missing from Postgres and re-added
    missing_in_bigquery: list[str] = []
    unsupported_types: list[SchemaSyncColumn] = []


class ClearDataRequest(BaseModel):
    confirmation: str  # must equal the exact phrase to proceed


class ClearDataResult(BaseModel):
    cleared: bool
    rows_deleted: dict[str, int]  # table -> rows removed
    total: int

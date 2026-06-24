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


class ClearDataRequest(BaseModel):
    confirmation: str  # must equal the exact phrase to proceed


class ClearDataResult(BaseModel):
    cleared: bool
    rows_deleted: dict[str, int]  # table -> rows removed
    total: int

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

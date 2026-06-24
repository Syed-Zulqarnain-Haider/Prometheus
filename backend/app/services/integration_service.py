"""Integration tab service: BigQuery key/connection status, a read-only BigQuery
'Test Connection', and the composed Integration status (connections + sync history).

Security invariants:
- The BigQuery reader service-account key is a MOUNTED FILE. Only its PRESENCE is
  checked for status (the file is never opened for a status), and the key path is never
  echoed back to the client.
- 'Test Connection' loads the key EXPLICITLY from ``Settings.bq_credentials_path`` — a
  SEPARATE identity from Firebase's ``GOOGLE_APPLICATION_CREDENTIALS`` — and performs a
  free, read-only dry-run query. It never modifies anything in BigQuery or Postgres.
- Nothing here ever returns a credential, key path, connection string, or raw provider
  error message; failures are sanitized to the exception's type name.
"""

from __future__ import annotations

import logging
from pathlib import Path

import anyio
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import SyncRun
from app.schemas.admin import SyncRunOut
from app.schemas.integration import BigQueryTestResult, IntegrationStatus
from app.schemas.system import ConnectionStatus
from app.services import system_service

log = logging.getLogger("app.integration")

# OAuth scope for the probe. The read-only boundary is enforced by the service
# account's IAM roles (BigQuery Data Viewer + Job User) — NOT by the OAuth scope — so the
# standard service-account scope is used; the SA still cannot write anything.
_BQ_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def _bq_key_present(settings: Settings) -> bool:
    """Is the BigQuery reader key mounted at the configured path? (presence only)."""
    try:
        return Path(settings.bq_credentials_path).is_file()
    except OSError:
        return False


def bigquery_status(settings: Settings) -> ConnectionStatus:
    """Presence-only BigQuery status for the Integration tab. Never reads the key or
    echoes its path/credential."""
    if _bq_key_present(settings):
        return ConnectionStatus(
            name="BigQuery",
            status="up",
            detail="Reader service-account key present at the configured path.",
        )
    return ConnectionStatus(
        name="BigQuery",
        status="not_configured",
        detail="No BigQuery reader key mounted — set BQ_CREDENTIALS_PATH and mount the key.",
    )


def _sync_out(run: SyncRun) -> SyncRunOut:
    return SyncRunOut(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        rows_loaded=run.rows_loaded,
        rows_previous=run.rows_previous,
        bq_built_at=run.bq_built_at,
        error_detail=run.error_detail,
    )


async def integration_status(
    db: AsyncSession, redis: Redis, settings: Settings
) -> IntegrationStatus:
    """Compose the Integration tab status: BigQuery key presence + Postgres/Redis pings
    + the most recent sync runs. Status/history only — never a credential."""
    recent = list(
        (await db.execute(select(SyncRun).order_by(SyncRun.id.desc()).limit(10))).scalars().all()
    )
    return IntegrationStatus(
        bigquery=bigquery_status(settings),
        postgres=await system_service.ping_postgres(db),
        redis=await system_service.ping_redis(redis),
        last_sync=_sync_out(recent[0]) if recent else None,
        recent_syncs=[_sync_out(run) for run in recent],
    )


def _run_bigquery_probe(key_path: str, project: str) -> tuple[bool, str]:
    """Blocking, READ-ONLY BigQuery reachability probe (run in a worker thread).

    Loads the reader key EXPLICITLY from ``key_path`` (never the ambient Firebase
    credentials) and runs a free dry-run ``SELECT 1`` — which validates auth + API
    reachability without executing a query or scanning any bytes. Returns
    ``(ok, sanitized_message)``; the message never contains a credential, path, or raw
    provider error.
    """
    try:
        # Lazy import: the BigQuery client lib ships only in the sync-enabled image, so a
        # plain API/dev environment reports an honest "library unavailable" instead of
        # failing at import time.
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except Exception:  # noqa: BLE001
        return (False, "BigQuery client library is not available in this environment.")

    try:
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=_BQ_SCOPES
        )
        client = bigquery.Client(project=project or None, credentials=credentials)
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        # Dry run: BigQuery validates the query + credentials but runs nothing and scans
        # zero bytes — an unambiguous read-only reachability check.
        client.query("SELECT 1", job_config=job_config, timeout=15)
        return (True, "BigQuery connection OK (read-only check passed).")
    except Exception as exc:  # noqa: BLE001 — sanitize: type name only, never the message
        log.warning("BigQuery test connection failed: %s", type(exc).__name__)
        return (False, f"BigQuery test failed ({type(exc).__name__}).")


async def test_bigquery(settings: Settings, project: str) -> BigQueryTestResult:
    """Run the read-only BigQuery probe. Honest result when the key is missing or the
    client library is unavailable — never a faked success."""
    if not _bq_key_present(settings):
        return BigQueryTestResult(
            ok=False,
            message=(
                "No BigQuery reader key mounted at the configured path. Mount the reader "
                "service-account key (BQ_CREDENTIALS_PATH) to enable BigQuery access."
            ),
        )
    ok, message = await anyio.to_thread.run_sync(
        _run_bigquery_probe, settings.bq_credentials_path, project
    )
    return BigQueryTestResult(ok=ok, message=message)

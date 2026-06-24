"""System health checks and on-demand sync trigger for the admin System tab.

Health checks are lightweight pings performed at request time. They return ONLY
up/down/not_configured + latency — never a connection string, host, or credential.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from time import perf_counter

import anyio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.system import ConnectionStatus, SyncTriggerResult, SystemHealth

log = logging.getLogger("app.system")


def _ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 1)


async def ping_postgres(db: AsyncSession) -> ConnectionStatus:
    """Lightweight Postgres liveness ping — up/down + latency only, never the DSN.
    Reused by the Integration tab status."""
    start = perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        return ConnectionStatus(name="PostgreSQL", status="up", latency_ms=_ms(start))
    except Exception:  # noqa: BLE001 — report down, never leak the error/DSN
        log.exception("Postgres health check failed")
        return ConnectionStatus(name="PostgreSQL", status="down")


async def ping_redis(redis: Redis) -> ConnectionStatus:
    """Lightweight Redis liveness ping — up/down + latency only, never the URL.
    Reused by the Integration tab status."""
    start = perf_counter()
    try:
        await redis.ping()
        return ConnectionStatus(name="Redis", status="up", latency_ms=_ms(start))
    except Exception:  # noqa: BLE001
        log.exception("Redis health check failed")
        return ConnectionStatus(name="Redis", status="down")


def _bigquery_status(settings: Settings) -> ConnectionStatus:
    # By design the API never queries BigQuery (only the sync job does), so we report
    # CONFIGURATION presence — not a live query — and never echo the project/credential.
    if settings.bigquery_project:
        return ConnectionStatus(
            name="BigQuery",
            status="up",
            detail="Configured for the sync pipeline (the API never queries BigQuery directly).",
        )
    return ConnectionStatus(
        name="BigQuery",
        status="not_configured",
        detail="No BigQuery data source configured for this environment.",
    )


async def check_connections(db: AsyncSession, redis: Redis, settings: Settings) -> SystemHealth:
    return SystemHealth(
        postgres=await ping_postgres(db),
        redis=await ping_redis(redis),
        bigquery=_bigquery_status(settings),
    )


def _post_trigger(url: str, token: str | None) -> tuple[bool, str]:
    """Blocking POST to the operator-configured sync-trigger URL (run in a thread)."""
    request = urllib.request.Request(url, data=b"{}", method="POST")  # noqa: S310 — operator URL
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310
            return (200 <= resp.status < 300, f"HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        return (False, f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        return (False, type(exc).__name__)


async def run_sync_now(settings: Settings) -> SyncTriggerResult:
    """Trigger the deployed sync job on demand.

    Local / no data source configured → an honest 'not configured' result (never a
    faked success). When ``SYNC_TRIGGER_URL`` is wired at deployment (the Cloud Run
    Job execution endpoint), this actually POSTs to it to start the sync.
    """
    if not settings.sync_trigger_url:
        return SyncTriggerResult(
            triggered=False,
            configured=False,
            message=(
                "Data source not configured — connect BigQuery and the sync job "
                "(SYNC_TRIGGER_URL) at deployment to enable on-demand sync."
            ),
        )
    ok, detail = await anyio.to_thread.run_sync(
        _post_trigger, settings.sync_trigger_url, settings.sync_trigger_token
    )
    if ok:
        return SyncTriggerResult(triggered=True, configured=True, message="Sync triggered.")
    return SyncTriggerResult(
        triggered=False, configured=True, message=f"Sync trigger failed ({detail})."
    )

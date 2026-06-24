"""System health checks and on-demand sync trigger for the admin System tab.

Health checks are lightweight pings performed at request time. They return ONLY
up/down/not_configured + latency — never a connection string, host, or credential.
"""

from __future__ import annotations

import logging
from time import perf_counter

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.system import ConnectionStatus, SystemHealth

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

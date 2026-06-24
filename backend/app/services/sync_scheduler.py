"""In-process daily-sync scheduler.

A lightweight asyncio loop (started from the app lifespan) that, once a minute, reads the
operational settings and — when ``sync_enabled`` and the clock has reached
``sync_schedule_time`` in ``sync_timezone`` — fires the sync via ``sync_service.run_sync``.

It is safe to run this loop on EVERY backend instance: ``run_sync`` takes a Postgres
advisory lock and re-checks ``skip_if_ran_after`` under it, so the daily sync fires
exactly once per day no matter how many instances tick simultaneously. Each tick is
isolated — an error is logged and the loop continues; it never crashes the app.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.services import settings_service, sync_service

log = logging.getLogger("app.scheduler")

_TICK_SECONDS = 60


async def _tick(sessionmaker: async_sessionmaker[Any], settings: Settings) -> None:
    """One scheduler iteration: fire the sync if it is enabled and due today."""
    async with sessionmaker() as db:
        if not bool(await settings_service.get_value(db, "sync_enabled")):
            return
        hhmm = str(await settings_service.get_value(db, "sync_schedule_time"))
        tz_name = str(await settings_service.get_value(db, "sync_timezone"))
        gcp_project = str(await settings_service.get_value(db, "gcp_project"))
        bq_view = str(await settings_service.get_value(db, "bq_view"))

    due, scheduled_utc = sync_service.is_due(datetime.now(UTC), hhmm, tz_name)
    if not due:
        return

    result = await sync_service.run_sync(
        sessionmaker,
        settings,
        gcp_project=gcp_project,
        bq_view=bq_view,
        skip_if_ran_after=scheduled_utc,
    )
    if result.triggered:
        log.info("scheduled sync fired: %s", result.message)


async def scheduler_loop(
    sessionmaker: async_sessionmaker[Any],
    settings: Settings,
    *,
    tick_seconds: int = _TICK_SECONDS,
) -> None:
    """Run the scheduler until cancelled. Every tick is best-effort and never fatal."""
    log.info("daily sync scheduler started (tick=%ss)", tick_seconds)
    while True:
        try:
            await _tick(sessionmaker, settings)
        except asyncio.CancelledError:
            log.info("daily sync scheduler stopping")
            raise
        except Exception:  # noqa: BLE001 — a tick must never kill the loop
            log.exception("scheduler tick failed")
        await asyncio.sleep(tick_seconds)

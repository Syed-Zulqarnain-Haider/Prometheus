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
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.services import alerts_service, settings_service, sync_service

log = logging.getLogger("app.scheduler")

_TICK_SECONDS = 60
# Fire alerts this long after the sync schedule time, so the fact table is fresh first.
_ALERT_DELAY = timedelta(minutes=15)
# Once-per-day guard (per process). Duplicate alerts across multiple instances are possible but
# harmless; a DB marker could dedup if that ever matters.
_last_alert_date: date | None = None


async def _maybe_evaluate_alerts(
    sessionmaker: async_sessionmaker[Any], settings: Settings, now: datetime
) -> None:
    """Evaluate anomaly alerts once per day, ~15 min after the scheduled sync (so the data is
    fresh). Best-effort and isolated — never affects the sync tick."""
    global _last_alert_date
    async with sessionmaker() as db:
        if not bool(await settings_service.get_value(db, "alerts_enabled")):
            return
        hhmm = str(await settings_service.get_value(db, "sync_schedule_time"))
        tz_name = str(await settings_service.get_value(db, "sync_timezone"))
        _, scheduled_utc = sync_service.is_due(now, hhmm, tz_name)
        if now < scheduled_utc + _ALERT_DELAY or _last_alert_date == now.date():
            return
        fired = await alerts_service.evaluate_and_notify(db, settings)
    _last_alert_date = now.date()
    if fired:
        log.info("alerts fired: %s", ", ".join(a["key"] for a in fired))


async def _tick(sessionmaker: async_sessionmaker[Any], settings: Settings) -> None:
    """One scheduler iteration: fire the sync if it is enabled and due today."""
    async with sessionmaker() as db:
        if not bool(await settings_service.get_value(db, "sync_enabled")):
            return
        hhmm = str(await settings_service.get_value(db, "sync_schedule_time"))
        tz_name = str(await settings_service.get_value(db, "sync_timezone"))
        gcp_project = str(await settings_service.get_value(db, "gcp_project"))
        bq_view = str(await settings_service.get_value(db, "bq_view"))
        window_days = int(await settings_service.get_value(db, "sync_window_days"))

    due, scheduled_utc = sync_service.is_due(datetime.now(UTC), hhmm, tz_name)
    if not due:
        return

    # The scheduled daily run is always the rolling-window incremental overwrite.
    result = await sync_service.run_sync(
        sessionmaker,
        settings,
        gcp_project=gcp_project,
        bq_view=bq_view,
        mode="incremental",
        window_days=window_days,
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
        try:
            await _maybe_evaluate_alerts(sessionmaker, settings, datetime.now(UTC))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — alert eval must never kill the loop
            log.exception("alert evaluation failed")
        await asyncio.sleep(tick_seconds)

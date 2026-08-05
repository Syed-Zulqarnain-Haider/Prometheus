"""In-process daily-sync scheduler.

A lightweight asyncio loop (started from the app lifespan) that, once a minute, reads the
operational settings and — when ``sync_enabled`` and the clock has reached
``sync_schedule_time`` in ``sync_timezone`` — fires the sync via ``sync_service.run_sync``.

It is safe to run this loop on EVERY backend instance: ``run_sync`` takes a Postgres
advisory lock and re-checks ``skip_if_ran_after`` under it, so the daily sync fires
exactly once per day no matter how many instances tick simultaneously. Each tick is
isolated — an error is logged and the loop continues; it never crashes the app.

EVERY tick outcome is logged, not just a successful fire: "not configured", "already ran",
"already running" and "trigger failed" used to be silent, which is how a broken sync stayed
invisible for a day. Reasons are deduped so a standing condition logs once, not every tick.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.models import JobRun
from app.services import (
    alerts_service,
    digest_service,
    report_delivery_service,
    settings_service,
    sync_service,
)

log = logging.getLogger("app.scheduler")

_TICK_SECONDS = 60
# Fire alerts this long after the sync schedule time, so the fact table is fresh first.
_ALERT_DELAY = timedelta(minutes=15)
_POST_SYNC_JOB = "post_sync_routines"

# Last non-fire reason, so a persistent condition is logged ONCE rather than every tick.
_last_skip_reason: str | None = None


async def _claim_daily_job(sessionmaker: async_sessionmaker[Any], job: str, run_date: date) -> bool:
    """Atomically claim ``job`` for ``run_date`` across ALL instances and restarts. Returns True
    only for the single winner (INSERT ... ON CONFLICT DO NOTHING). This is what makes the daily
    routines fire exactly once cluster-wide — not once per process."""
    async with sessionmaker() as db:
        stmt = (
            pg_insert(JobRun)
            .values(job=job, run_date=run_date)
            .on_conflict_do_nothing(index_elements=["job", "run_date"])
            .returning(JobRun.job)
        )
        won = (await db.execute(stmt)).first() is not None
        await db.commit()
        return won


async def _maybe_evaluate_alerts(
    sessionmaker: async_sessionmaker[Any], settings: Settings, now: datetime
) -> None:
    """Run the daily post-sync routines (anomaly alerts + digest) once per day, ~15 min after
    the scheduled sync so the fact table is fresh. Best-effort and isolated — never affects the
    sync tick. Deduped by a DB claim, so it fires exactly ONCE across instances and restarts."""
    async with sessionmaker() as db:
        alerts_on = bool(await settings_service.get_value(db, "alerts_enabled"))
        digest_on = bool(await settings_service.get_value(db, "digest_enabled"))
        if not alerts_on and not digest_on:
            return
        hhmm = str(await settings_service.get_value(db, "sync_schedule_time"))
        tz_name = str(await settings_service.get_value(db, "sync_timezone"))
    _, scheduled_utc = sync_service.is_due(now, hhmm, tz_name)
    if now < scheduled_utc + _ALERT_DELAY:
        return
    # Claim the day BEFORE doing any work — only the winning instance proceeds.
    if not await _claim_daily_job(sessionmaker, _POST_SYNC_JOB, now.date()):
        return

    async with sessionmaker() as db:
        fired: list[dict[str, Any]] = []
        if alerts_on:
            try:
                fired = await alerts_service.evaluate_and_notify(db, settings)
            except Exception:  # noqa: BLE001 — must never block the digest or the loop
                log.exception("alert evaluation failed")
        # The digest is gated by its OWN setting and runs independently of alerts.
        if digest_on:
            try:
                await digest_service.build_and_send(db, settings)
            except Exception:  # noqa: BLE001 — the digest must never block the loop
                log.exception("digest send failed")
    if fired:
        log.info("alerts fired: %s", ", ".join(a["key"] for a in fired))


async def _tick(sessionmaker: async_sessionmaker[Any], settings: Settings) -> None:
    """One scheduler iteration: fire the sync if it is enabled and due today."""
    global _last_skip_reason
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
        _last_skip_reason = None
        log.info("scheduled sync fired: %s", result.message)
        return

    # Every non-fire outcome is surfaced. Deduped by reason: a standing condition (e.g.
    # "already ran for this period", which holds from the schedule time until midnight)
    # logs once instead of once per 60s tick.
    if result.message != _last_skip_reason:
        _last_skip_reason = result.message
        if not result.configured:
            log.error("scheduled sync NOT CONFIGURED: %s", result.message)
        elif result.message.startswith("Sync trigger failed"):
            log.error("scheduled sync TRIGGER FAILED: %s", result.message)
        else:
            log.info("scheduled sync skipped: %s", result.message)


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
        try:
            # Scheduled report emails: each schedule self-guards on its own hour/day + a
            # once-per-day claim, so calling this every tick is cheap and multi-instance safe.
            await report_delivery_service.evaluate_due(sessionmaker, settings, datetime.now(UTC))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — report delivery must never kill the loop
            log.exception("scheduled report evaluation failed")
        await asyncio.sleep(tick_seconds)

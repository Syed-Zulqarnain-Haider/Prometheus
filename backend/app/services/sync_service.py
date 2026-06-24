"""Sync orchestration shared by the daily scheduler and the manual 'Run Sync Now'.

Execution model (owner decision): if ``SYNC_TRIGGER_URL`` is configured, POST to it (the
deployed Cloud Run Job execution endpoint); otherwise, if the backend is provisioned to
run the sync locally (BigQuery reader key mounted + ``SYNC_PG_DSN`` + a GCP project), run
the vendored ``sync/sync_job.py`` as a subprocess; otherwise report an honest
'not configured' result (never a faked success).

Exactly-once-per-day is guaranteed regardless of how many backend instances run the
scheduler: every run is wrapped in a Postgres SESSION advisory lock, and the scheduler
additionally passes ``skip_if_ran_after`` so that — re-checked UNDER the lock — a second
instance that wins the race still won't double-run for the same day.

Security: the subprocess loads the BigQuery key EXPLICITLY from ``bq_credentials_path``
(set as the child's ``GOOGLE_APPLICATION_CREDENTIALS`` — a SEPARATE identity from the
backend's own Firebase credentials, which are left untouched). Child stdout/stderr are
discarded so a DSN or credential can never reach the backend logs; the authoritative,
sanitized record is the ``sync_runs`` row the job writes itself.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anyio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.schemas.system import SyncTriggerResult

log = logging.getLogger("app.sync")

# The vendored sync job inside the backend image (backend/sync/sync_job.py).
_SYNC_JOB = Path(__file__).resolve().parents[2] / "sync" / "sync_job.py"

# Fixed 64-bit key for the daily-sync session advisory lock ("prom").
_SYNC_LOCK_KEY = 0x70726F6D

# Strong refs to in-flight local-sync finalizers so the loop never GCs them mid-run.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()

_NOT_CONFIGURED_MSG = (
    "Data source not configured — set SYNC_TRIGGER_URL, or mount the BigQuery reader key "
    "(BQ_CREDENTIALS_PATH), set SYNC_PG_DSN, and a GCP project, to enable sync."
)


def is_due(now_utc: datetime, schedule_hhmm: str, tz_name: str) -> tuple[bool, datetime]:
    """Pure helper for the scheduler.

    Returns ``(due, scheduled_utc)`` where ``scheduled_utc`` is *today's* scheduled run
    instant (the ``HH:MM`` wall-clock time in ``tz_name``, as UTC) and ``due`` is whether
    ``now_utc`` has reached it. 'Due' uses >= (not ==) so a missed tick or a cold start
    after the scheduled time still triggers a catch-up run for the day — the
    once-per-day guarantee comes from the advisory lock + ``skip_if_ran_after``.
    """
    try:
        tz = ZoneInfo(tz_name)
        hours, minutes = (int(part) for part in schedule_hhmm.split(":"))
        now_local = now_utc.astimezone(tz)
        scheduled_local = now_local.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        scheduled_utc = scheduled_local.astimezone(UTC)
    except Exception:  # noqa: BLE001 — a malformed schedule/tz simply means "not due"
        log.exception("is_due: bad schedule (%r) or timezone (%r)", schedule_hhmm, tz_name)
        return (False, now_utc)
    return (now_utc >= scheduled_utc, scheduled_utc)


def _local_run_configured(settings: Settings, gcp_project: str) -> bool:
    """Can the backend run the sync itself? Needs the sync DSN, a GCP project, and the
    BigQuery reader key actually present on disk."""
    if not settings.sync_pg_dsn or not gcp_project:
        return False
    try:
        return Path(settings.bq_credentials_path).is_file()
    except OSError:
        return False


def _child_env(settings: Settings, gcp_project: str, bq_view: str) -> dict[str, str]:
    """Environment for the vendored sync subprocess. Overrides GOOGLE_APPLICATION_
    CREDENTIALS with the BigQuery reader key (NOT the backend's Firebase key)."""
    env = dict(os.environ)
    env["GOOGLE_APPLICATION_CREDENTIALS"] = settings.bq_credentials_path
    env["GCP_PROJECT"] = gcp_project
    env["BQ_VIEW"] = bq_view
    env["PG_DSN"] = settings.sync_pg_dsn or ""
    env["REDIS_URL"] = settings.redis_url
    return env


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
    except Exception as exc:  # noqa: BLE001 — sanitize: type name only, never the URL/error
        return (False, type(exc).__name__)


async def _spawn_local(
    settings: Settings, gcp_project: str, bq_view: str
) -> asyncio.subprocess.Process:
    """Spawn the vendored sync subprocess. stdout/stderr are discarded so no DSN or
    credential can leak into the backend logs; the job records its own ``sync_runs`` row."""
    return await asyncio.create_subprocess_exec(
        sys.executable,
        str(_SYNC_JOB),
        env=_child_env(settings, gcp_project, bq_view),
        cwd=str(_SYNC_JOB.parent),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def _release_and_close(db: AsyncSession) -> None:
    """Release the advisory lock and return the connection to the pool."""
    try:
        await db.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": _SYNC_LOCK_KEY})
    finally:
        await db.close()


async def _finalize_local(proc: asyncio.subprocess.Process, lock_db: AsyncSession) -> None:
    """Background: await the running sync, then release the lock it holds. Holding the
    lock for the subprocess's lifetime is what makes a concurrent run report 'already
    running' until this one finishes."""
    try:
        returncode = await proc.wait()
        if returncode != 0:
            log.warning("local sync exited with code %s", returncode)
    finally:
        await _release_and_close(lock_db)


async def run_sync(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    gcp_project: str,
    bq_view: str,
    skip_if_ran_after: datetime | None = None,
) -> SyncTriggerResult:
    """Trigger the sync once, under a Postgres advisory lock. Returns as soon as the sync
    is *kicked off* (never blocking on a long run): the URL path POSTs and returns; the
    local path spawns the subprocess and hands the lock to a background finalizer. Honest
    'not configured' when no execution path is available — never a faked success.

    ``skip_if_ran_after`` (scheduler only): if a ``sync_runs`` row already started at/after
    this instant, skip — so the daily run fires exactly once even across instances.
    """
    trigger_url = settings.sync_trigger_url
    has_local = _local_run_configured(settings, gcp_project)
    if not trigger_url and not has_local:
        return SyncTriggerResult(triggered=False, configured=False, message=_NOT_CONFIGURED_MSG)

    lock_db = sessionmaker()
    got = await lock_db.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SYNC_LOCK_KEY})
    if not got:
        await lock_db.close()
        return SyncTriggerResult(
            triggered=False, configured=True, message="A sync is already running."
        )

    handed_off = False
    try:
        if skip_if_ran_after is not None:
            already = await lock_db.scalar(
                text("SELECT 1 FROM sync_runs WHERE started_at >= :t LIMIT 1"),
                {"t": skip_if_ran_after},
            )
            if already:
                return SyncTriggerResult(
                    triggered=False, configured=True, message="A sync already ran for this period."
                )
        if trigger_url:  # delegate to the configured Cloud Run Job execution endpoint
            ok, detail = await anyio.to_thread.run_sync(
                _post_trigger, trigger_url, settings.sync_trigger_token
            )
            if ok:
                return SyncTriggerResult(triggered=True, configured=True, message="Sync triggered.")
            return SyncTriggerResult(
                triggered=False, configured=True, message=f"Sync trigger failed ({detail})."
            )
        # Local: kick off the subprocess and hand the lock to a background finalizer so
        # the request/scheduler tick returns immediately instead of blocking on the run.
        proc = await _spawn_local(settings, gcp_project, bq_view)
        task = asyncio.create_task(_finalize_local(proc, lock_db))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        handed_off = True
        return SyncTriggerResult(triggered=True, configured=True, message="Sync started.")
    finally:
        if not handed_off:
            await _release_and_close(lock_db)

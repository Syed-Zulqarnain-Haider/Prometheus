"""Sync orchestration shared by the daily scheduler and the manual 'Run Sync Now'.

Execution model (owner decision): if ``SYNC_TRIGGER_URL`` is configured, POST to it (the
deployed Cloud Run Job execution endpoint); otherwise, if the backend is provisioned to
run the sync locally (BigQuery reader key mounted + ``SYNC_PG_DSN`` + a GCP project), run
the vendored ``sync/sync_job.py`` as a subprocess; otherwise report an honest
'not configured' result (never a faked success).

Locking: the backend takes a Postgres SESSION advisory lock ONLY to serialize the trigger
decision, and RELEASES it before the spawned job starts. ``sync/sync_job.py`` takes the
same key itself and no-ops if it cannot get it, so a lock held across the spawn made every
backend-triggered run a silent no-op - the child always lost to its own parent.

Exactly-once-per-day is guaranteed regardless of how many backend instances run the
scheduler: the advisory lock serializes triggers, the job's own lock serializes runs, and
the scheduler additionally passes ``skip_if_ran_after`` so that - re-checked UNDER the
lock - a second instance that wins the race still won't double-run for the day. That check is
status-aware: a SUCCESSFUL run ends the day, an in-flight run blocks while it lasts, but a
FAILED run is retried (after a backoff) instead of wedging the pipeline until tomorrow.

Security: the subprocess loads the BigQuery key EXPLICITLY from ``bq_credentials_path``
(set as the child's ``GOOGLE_APPLICATION_CREDENTIALS`` - a SEPARATE identity from the
backend's own Firebase credentials, which are left untouched). Child stdout/stderr are
STREAMED INTO THE BACKEND LOG (prefixed ``[sync]``): the job logs no DSN or credential, only
mode/warnings/row counts, and discarding them previously made a day-long outage invisible.
The authoritative, sanitized record remains the ``sync_runs`` row the job writes itself.
"""

from __future__ import annotations

import asyncio
import json
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

# Scheduler skip rule. A run at/after the scheduled instant blocks a re-fire ONLY when it
# succeeded, is genuinely still in flight, or failed very recently:
#   * status='success'                      -> today's run is done, stop for the day
#   * status='running' and started < 2h ago -> a real run is in progress (a stranded
#                                              'running' row therefore cannot wedge us)
#   * any run started < 30 min ago          -> backoff, so a crash retries periodically
#                                              instead of every 60s (or never at all)
_SKIP_SQL = (
    "SELECT 1 FROM sync_runs WHERE started_at >= :t AND ("
    "  status = 'success'"
    "  OR (status = 'running' AND started_at > now() - interval '2 hours')"
    "  OR started_at > now() - interval '30 minutes'"
    ") LIMIT 1"
)

_NOT_CONFIGURED_MSG = (
    "Data source not configured - set SYNC_TRIGGER_URL, or mount the BigQuery reader key "
    "(BQ_CREDENTIALS_PATH), set SYNC_PG_DSN, and a GCP project, to enable sync."
)


def is_due(now_utc: datetime, schedule_hhmm: str, tz_name: str) -> tuple[bool, datetime]:
    """Pure helper for the scheduler.

    Returns ``(due, scheduled_utc)`` where ``scheduled_utc`` is *today's* scheduled run
    instant (the ``HH:MM`` wall-clock time in ``tz_name``, as UTC) and ``due`` is whether
    ``now_utc`` has reached it. 'Due' uses >= (not ==) so a missed tick or a cold start
    after the scheduled time still triggers a catch-up run for the day - the
    once-per-day guarantee comes from the advisory lock + ``skip_if_ran_after``.
    """
    try:
        tz = ZoneInfo(tz_name)
        hours, minutes = (int(part) for part in schedule_hhmm.split(":"))
        now_local = now_utc.astimezone(tz)
        # Build today's wall-clock target FRESH with the zone so zoneinfo resolves the
        # correct UTC offset for that instant - .replace(hour=...) on an already-localized
        # datetime would reuse *now's* offset and be wrong by an hour on DST-transition days.
        scheduled_local = datetime(
            now_local.year, now_local.month, now_local.day, hours, minutes, tzinfo=tz
        )
        scheduled_utc = scheduled_local.astimezone(UTC)
    except Exception:  # noqa: BLE001 - a malformed schedule/tz simply means "not due"
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


def _child_env(
    settings: Settings,
    gcp_project: str,
    bq_view: str,
    mode: str,
    window_days: int,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, str]:
    """Environment for the vendored sync subprocess. Overrides GOOGLE_APPLICATION_
    CREDENTIALS with the BigQuery reader key (NOT the backend's Firebase key)."""
    env = dict(os.environ)
    env["GOOGLE_APPLICATION_CREDENTIALS"] = settings.bq_credentials_path
    env["GCP_PROJECT"] = gcp_project
    env["BQ_VIEW"] = bq_view
    env["PG_DSN"] = settings.sync_pg_dsn or ""
    env["REDIS_URL"] = settings.redis_url
    env["SYNC_MODE"] = mode
    env["SYNC_WINDOW_DAYS"] = str(window_days)
    env["SYNC_START_DATE"] = start_date or ""
    env["SYNC_END_DATE"] = end_date or ""
    # Unbuffered, so the child's log lines reach our reader as they happen rather than
    # only at exit - a job that dies early must still show why.
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _post_trigger(
    url: str, token: str | None, mode: str = "incremental", window_days: int = 40
) -> tuple[bool, str]:
    """Blocking POST to the operator-configured sync-trigger URL (run in a thread). The mode
    + window are sent in the body so a Cloud Run Job endpoint can honor them (forward-compat;
    the vendored local job reads them from env)."""
    body = json.dumps({"mode": mode, "window_days": window_days}).encode()
    request = urllib.request.Request(url, data=body, method="POST")  # noqa: S310 - operator URL
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310
            return (200 <= resp.status < 300, f"HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        return (False, f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001 - sanitize: type name only, never the URL/error
        return (False, type(exc).__name__)


async def _spawn_local(
    settings: Settings,
    gcp_project: str,
    bq_view: str,
    mode: str,
    window_days: int,
    start_date: str | None,
    end_date: str | None,
) -> asyncio.subprocess.Process:
    """Spawn the vendored sync subprocess with its output piped back to us, so
    ``_finalize_local`` can stream the job's own log into the backend log."""
    log.info("spawning local sync: mode=%s window_days=%s view=%s", mode, window_days, bq_view)
    return await asyncio.create_subprocess_exec(
        sys.executable,
        str(_SYNC_JOB),
        env=_child_env(settings, gcp_project, bq_view, mode, window_days, start_date, end_date),
        cwd=str(_SYNC_JOB.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


async def _release_and_close(db: AsyncSession) -> None:
    """Release the advisory lock and return the connection to the pool."""
    try:
        await db.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": _SYNC_LOCK_KEY})
    finally:
        await db.close()


async def _drain_local(proc: asyncio.subprocess.Process) -> None:
    """Background: stream the sync's own output into the backend log and await its exit.

    Draining the pipe is REQUIRED, not just useful: with ``stdout=PIPE`` an undrained pipe
    would eventually block the child. It is also the only way a crash before the job writes
    its ``sync_runs`` row is ever visible.

    This deliberately does NOT hold the advisory lock: the job takes the SAME key itself
    and no-ops when it cannot acquire it, so ``run_sync`` must release before the child
    starts. The child's lock is the real mutual exclusion for the duration of a run.
    """
    try:
        # getattr, not proc.stdout: a stubbed process in tests may not define the attribute
        # at all, and losing the exit-code check to an AttributeError would be silly.
        stdout = getattr(proc, "stdout", None)
        if stdout is not None:
            async for raw in stdout:
                line = raw.decode(errors="replace").rstrip()
                if line:
                    log.info("[sync] %s", line)
        returncode = await proc.wait()
        if returncode != 0:
            log.error("local sync exited with code %s", returncode)
        else:
            log.info("local sync finished cleanly")
    except Exception:  # noqa: BLE001 - a drain failure must never escape the background task
        log.exception("local sync output drain failed")


async def run_sync(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    gcp_project: str,
    bq_view: str,
    mode: str = "incremental",
    window_days: int = 40,
    start_date: str | None = None,
    end_date: str | None = None,
    skip_if_ran_after: datetime | None = None,
) -> SyncTriggerResult:
    """Trigger the sync once, under a Postgres advisory lock. Returns as soon as the sync
    is *kicked off* (never blocking on a long run): the URL path POSTs and returns; the
    local path spawns the subprocess and hands the lock to a background finalizer. Honest
    'not configured' when no execution path is available - never a faked success.

    ``skip_if_ran_after`` (scheduler only): skip when a ``sync_runs`` row at/after this
    instant shows the day is already handled - see ``_SKIP_SQL``. A FAILED run does not
    count as handled, so a crash is retried rather than blocking until tomorrow.
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
            already = await lock_db.scalar(text(_SKIP_SQL), {"t": skip_if_ran_after})
            if already:
                return SyncTriggerResult(
                    triggered=False, configured=True, message="A sync already ran for this period."
                )
        if trigger_url:  # delegate to the configured Cloud Run Job execution endpoint
            ok, detail = await anyio.to_thread.run_sync(
                _post_trigger, trigger_url, settings.sync_trigger_token, mode, window_days
            )
            if ok:
                return SyncTriggerResult(triggered=True, configured=True, message="Sync triggered.")
            return SyncTriggerResult(
                triggered=False, configured=True, message=f"Sync trigger failed ({detail})."
            )
        # Local: kick off the subprocess and hand the lock to a background finalizer so
        # the request/scheduler tick returns immediately instead of blocking on the run.
        proc = await _spawn_local(
            settings, gcp_project, bq_view, mode, window_days, start_date, end_date
        )
        # Release OUR lock BEFORE the child reaches for it. sync_job.py takes the SAME key
        # (its SYNC_ADVISORY_LOCK_KEY == _SYNC_LOCK_KEY) and cleanly no-ops when it cannot
        # acquire it - so holding this across the spawn made EVERY backend-triggered run a
        # silent do-nothing ("another sync holds the advisory lock - skipping"). Our lock
        # only serializes the trigger decision above; the child's lock guards the run.
        await _release_and_close(lock_db)
        handed_off = True
        task = asyncio.create_task(_drain_local(proc))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        return SyncTriggerResult(triggered=True, configured=True, message="Sync started.")
    finally:
        if not handed_off:
            await _release_and_close(lock_db)

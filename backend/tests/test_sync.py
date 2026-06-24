"""Tests for PR 2: the daily-sync scheduler + manual 'Run Sync Now'.

Covers the pure ``is_due`` scheduling math, the advisory-lock-guarded ``run_sync``
(not-configured, already-running, delegate-to-URL, and the scheduler's exactly-once
``skip_if_ran_after`` gate), and the scheduler tick's enable/due decision. The local
subprocess path and the trigger POST are stubbed so no real sync or network runs.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.schemas.system import SyncTriggerResult
from app.services import settings_service, sync_scheduler, sync_service
from sqlalchemy import text

from tests.conftest import MetricsEnv, _metrics_uid


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(update=overrides)


def _admin_id() -> uuid.UUID:
    return uuid.UUID(_metrics_uid("admin"))


# ── is_due (pure scheduling math) ─────────────────────────────────────────────
def test_is_due_before_at_and_after() -> None:
    assert sync_service.is_due(datetime(2026, 6, 24, 5, 59, tzinfo=UTC), "06:00", "UTC")[0] is False
    assert sync_service.is_due(datetime(2026, 6, 24, 6, 0, tzinfo=UTC), "06:00", "UTC")[0] is True
    assert sync_service.is_due(datetime(2026, 6, 24, 6, 1, tzinfo=UTC), "06:00", "UTC")[0] is True


def test_is_due_respects_timezone() -> None:
    # 06:00 America/New_York in June is EDT (UTC-4) → 10:00 UTC.
    tz = "America/New_York"
    before, scheduled = sync_service.is_due(datetime(2026, 6, 24, 9, 59, tzinfo=UTC), "06:00", tz)
    after, _ = sync_service.is_due(datetime(2026, 6, 24, 10, 1, tzinfo=UTC), "06:00", tz)
    assert before is False
    assert after is True
    assert scheduled == datetime(2026, 6, 24, 10, 0, tzinfo=UTC)


def test_is_due_handles_dst_transition_day() -> None:
    # US spring-forward 2026-03-08: 02:00 EST -> 03:00 EDT. 06:00 that day is EDT (UTC-4)
    # = 10:00 UTC. now = 06:00 UTC = 01:00 EST (before the jump). The buggy .replace() would
    # reuse the EST offset and wrongly compute 11:00 UTC.
    now = datetime(2026, 3, 8, 6, 0, tzinfo=UTC)
    due, scheduled = sync_service.is_due(now, "06:00", "America/New_York")
    assert scheduled == datetime(2026, 3, 8, 10, 0, tzinfo=UTC)
    assert due is False  # 06:00 UTC is before the 10:00 UTC scheduled instant


def test_is_due_bad_inputs_are_not_due() -> None:
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    assert sync_service.is_due(now, "06:00", "Not/AZone")[0] is False
    assert sync_service.is_due(now, "not-a-time", "UTC")[0] is False


# ── run_sync: honest 'not configured' ─────────────────────────────────────────
async def test_run_sync_not_configured(metrics_env: MetricsEnv) -> None:
    result = await sync_service.run_sync(
        metrics_env.sessionmaker,
        _settings(sync_trigger_url=None, sync_pg_dsn=None),
        gcp_project="",
        bq_view="proj.ds.v1",
    )
    assert result.triggered is False
    assert result.configured is False
    assert "not configured" in result.message.lower()


# ── run_sync: delegate to the trigger URL (stubbed) ───────────────────────────
async def test_run_sync_delegates_to_trigger_url(metrics_env: MetricsEnv, monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_post(url: str, token: str | None) -> tuple[bool, str]:
        calls.append((url, token))
        return (True, "HTTP 200")

    monkeypatch.setattr(sync_service, "_post_trigger", fake_post)
    settings = _settings(sync_trigger_url="https://trigger.example/run", sync_trigger_token="tok")
    result = await sync_service.run_sync(
        metrics_env.sessionmaker, settings, gcp_project="proj", bq_view="proj.ds.v1"
    )
    assert result.triggered is True
    assert result.message == "Sync triggered."
    assert calls == [("https://trigger.example/run", "tok")]


# ── run_sync: advisory lock prevents concurrent runs ──────────────────────────
async def test_run_sync_respects_advisory_lock(metrics_env: MetricsEnv, monkeypatch) -> None:
    monkeypatch.setattr(sync_service, "_post_trigger", lambda url, token: (True, "HTTP 200"))
    settings = _settings(sync_trigger_url="https://trigger.example/run")

    # Hold the same advisory lock on a separate connection; run_sync opens its own.
    async with metrics_env.sessionmaker() as holder:
        got = await holder.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": sync_service._SYNC_LOCK_KEY}
        )
        assert got is True
        result = await sync_service.run_sync(
            metrics_env.sessionmaker, settings, gcp_project="proj", bq_view="proj.ds.v1"
        )
        assert result.triggered is False
        assert "already running" in result.message.lower()
        await holder.scalar(
            text("SELECT pg_advisory_unlock(:k)"), {"k": sync_service._SYNC_LOCK_KEY}
        )


# ── run_sync: scheduler's exactly-once skip_if_ran_after gate ──────────────────
async def test_run_sync_skips_when_a_run_already_started(
    metrics_env: MetricsEnv, monkeypatch
) -> None:
    monkeypatch.setattr(sync_service, "_post_trigger", lambda url, token: (True, "HTTP 200"))
    settings = _settings(sync_trigger_url="https://trigger.example/run")
    # The fixture seeded a sync_run "today"; a skip cutoff in the past finds it → skip.
    skipped = await sync_service.run_sync(
        metrics_env.sessionmaker,
        settings,
        gcp_project="proj",
        bq_view="proj.ds.v1",
        skip_if_ran_after=datetime(2000, 1, 1, tzinfo=UTC),
    )
    assert skipped.triggered is False
    assert "already ran" in skipped.message.lower()

    # A cutoff after every existing run → nothing found → it proceeds and fires.
    fired = await sync_service.run_sync(
        metrics_env.sessionmaker,
        settings,
        gcp_project="proj",
        bq_view="proj.ds.v1",
        skip_if_ran_after=datetime(2099, 1, 1, tzinfo=UTC),
    )
    assert fired.triggered is True


# ── run_sync: local path kicks off (fire-and-forget) and releases the lock ─────
async def test_run_sync_local_fire_and_forget(
    metrics_env: MetricsEnv, monkeypatch, tmp_path
) -> None:
    key = tmp_path / "bq.json"
    key.write_text("{}")  # presence only — never read
    settings = _settings(
        sync_trigger_url=None,
        sync_pg_dsn="postgresql://sync_service:x@db:5432/app",
        bq_credentials_path=str(key),
    )

    class FakeProc:
        async def wait(self) -> int:
            return 0

    async def fake_spawn(s: object, gcp: str, view: str) -> FakeProc:
        return FakeProc()

    monkeypatch.setattr(sync_service, "_spawn_local", fake_spawn)

    result = await sync_service.run_sync(
        metrics_env.sessionmaker, settings, gcp_project="proj", bq_view="proj.ds.v1"
    )
    assert result.triggered is True
    assert result.message == "Sync started."

    # The background finalizer releases the lock once the (fake) run finishes.
    await asyncio.gather(*list(sync_service._BACKGROUND_TASKS))
    async with metrics_env.sessionmaker() as db:
        free = await db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": sync_service._SYNC_LOCK_KEY}
        )
        assert free is True  # lock was released
        await db.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": sync_service._SYNC_LOCK_KEY})


# ── scheduler tick: disabled is a no-op; enabled + due fires run_sync ──────────
async def test_scheduler_tick_noop_when_disabled(metrics_env: MetricsEnv, monkeypatch) -> None:
    called: list[dict[str, object]] = []

    async def fake_run_sync(*args: object, **kwargs: object) -> SyncTriggerResult:
        called.append(kwargs)
        return SyncTriggerResult(triggered=True, configured=True, message="x")

    monkeypatch.setattr(sync_service, "run_sync", fake_run_sync)
    # sync_enabled defaults to False → the tick must not fire.
    await sync_scheduler._tick(metrics_env.sessionmaker, _settings())
    assert called == []


async def test_scheduler_tick_fires_when_enabled_and_due(
    metrics_env: MetricsEnv, monkeypatch
) -> None:
    captured: list[dict[str, object]] = []

    async def fake_run_sync(
        db: object,
        settings: object,
        *,
        gcp_project: str,
        bq_view: str,
        skip_if_ran_after: datetime | None = None,
    ) -> SyncTriggerResult:
        captured.append({"gcp_project": gcp_project, "bq_view": bq_view, "skip": skip_if_ran_after})
        return SyncTriggerResult(triggered=True, configured=True, message="fired")

    monkeypatch.setattr(sync_service, "run_sync", fake_run_sync)
    admin_id = _admin_id()
    async with metrics_env.sessionmaker() as db:
        await settings_service.set_value(db, "sync_enabled", True, admin_id)
        await settings_service.set_value(db, "sync_schedule_time", "00:00", admin_id)  # due all day
        await settings_service.set_value(db, "gcp_project", "my-project", admin_id)
        await settings_service.set_value(db, "bq_view", "proj.ds.daily_v1", admin_id)

    await sync_scheduler._tick(metrics_env.sessionmaker, _settings())

    assert len(captured) == 1
    assert captured[0]["gcp_project"] == "my-project"
    assert captured[0]["bq_view"] == "proj.ds.daily_v1"
    assert captured[0]["skip"] is not None  # the daily exactly-once cutoff

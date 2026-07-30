"""Tests for PR 3: the daily sync's APPEND/UPSERT load (data-critical).

The sync now MERGES a validated staging table into the live fact table by the natural
key (date, platform, app_key) instead of atomically swapping it — so Postgres keeps full
history even after BigQuery ages older days out. These tests exercise the EXACT SQL the
sync runs (``metric_registry.generate_upsert_sql``, loaded from the canonical repo-root
sync copy) against the test Postgres, with isolated tables so nothing else is touched.

Owner-required cases: first sync inserts; re-syncing a date updates in place with no
duplicates; a new date appends while old history is retained; and the fact table is
untouched until the UPSERT step (so a failed validation/integrity check leaves live data
intact).
"""

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import text

_FACT = "up_fact"
_STG = "up_stg"


def _load_sync_registry() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "sync" / "metric_registry.py"
    spec = importlib.util.spec_from_file_location("sync_metric_registry_upsert", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _setup(db: Any, reg: ModuleType) -> None:
    for table in (_FACT, _STG):
        await db.execute(text(f"DROP TABLE IF EXISTS {table}"))
    await db.execute(text(reg.generate_fact_ddl(_FACT)))
    await db.execute(text(reg.generate_fact_ddl(_STG)))
    await db.commit()


async def _insert(db: Any, table: str, **vals: Any) -> None:
    cols = ", ".join(vals)
    placeholders = ", ".join(f":{c}" for c in vals)
    await db.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"), vals)
    await db.commit()


async def _fact(db: Any) -> list[Any]:
    return (
        await db.execute(
            text(
                f"SELECT date, platform, canonical_key, app_name, pod, total_revenue_usd "
                f"FROM {_FACT} ORDER BY date, app_key"
            )
        )
    ).all()


async def _upsert(db: Any, reg: ModuleType) -> None:
    await db.execute(text(reg.generate_upsert_sql(_FACT, _STG)))
    await db.commit()


# ── first sync inserts ────────────────────────────────────────────────────────
async def test_first_sync_inserts(db_session: Any) -> None:
    reg = _load_sync_registry()
    await _setup(db_session, reg)
    await _insert(
        db_session,
        _STG,
        date=date(2026, 6, 1),
        platform="ios",
        canonical_key="appA",
        app_name="A",
        total_revenue_usd=100,
    )
    await _upsert(db_session, reg)

    rows = await _fact(db_session)
    assert len(rows) == 1
    assert rows[0].canonical_key == "appA"
    assert float(rows[0].total_revenue_usd) == 100.0


# ── re-syncing a date UPDATES in place (no duplicate), latest-wins on all cols ──
async def test_resync_same_date_updates_no_duplicates(db_session: Any) -> None:
    reg = _load_sync_registry()
    await _setup(db_session, reg)
    await _insert(
        db_session,
        _FACT,
        date=date(2026, 6, 1),
        platform="ios",
        canonical_key="appA",
        app_name="Old",
        pod="POD_A",
        total_revenue_usd=50,
    )
    await _insert(
        db_session,
        _STG,
        date=date(2026, 6, 1),
        platform="ios",
        canonical_key="appA",
        app_name="New",
        pod="POD_B",
        total_revenue_usd=999,
    )
    await _upsert(db_session, reg)

    rows = await _fact(db_session)
    assert len(rows) == 1  # updated in place, not duplicated
    assert float(rows[0].total_revenue_usd) == 999.0  # metric refreshed
    assert rows[0].app_name == "New"  # dimension refreshed (latest-wins)
    assert rows[0].pod == "POD_B"


# ── a new date APPENDS; history absent from staging is RETAINED ────────────────
async def test_new_date_appends_and_old_history_retained(db_session: Any) -> None:
    reg = _load_sync_registry()
    await _setup(db_session, reg)
    await _insert(
        db_session,
        _FACT,
        date=date(2026, 6, 1),
        platform="ios",
        canonical_key="appA",
        total_revenue_usd=50,
    )
    # Today's view only has June 2 (June 1 has aged out of BigQuery).
    await _insert(
        db_session,
        _STG,
        date=date(2026, 6, 2),
        platform="ios",
        canonical_key="appA",
        total_revenue_usd=70,
    )
    await _upsert(db_session, reg)

    rows = await _fact(db_session)
    assert len(rows) == 2
    assert [r.date for r in rows] == [date(2026, 6, 1), date(2026, 6, 2)]
    assert float(rows[0].total_revenue_usd) == 50.0  # old day retained untouched
    assert float(rows[1].total_revenue_usd) == 70.0  # new day appended


# ── the live fact table is UNTOUCHED until the UPSERT (abort-safety) ───────────
async def test_fact_untouched_until_upsert(db_session: Any) -> None:
    reg = _load_sync_registry()
    await _setup(db_session, reg)
    await _insert(
        db_session,
        _FACT,
        date=date(2026, 6, 1),
        platform="ios",
        canonical_key="appA",
        total_revenue_usd=50,
    )
    # Staging is loaded, but a failed validation/integrity check means we never UPSERT.
    await _insert(
        db_session,
        _STG,
        date=date(2026, 6, 1),
        platform="ios",
        canonical_key="appA",
        total_revenue_usd=999,
    )

    rows = await _fact(db_session)
    assert len(rows) == 1
    assert float(rows[0].total_revenue_usd) == 50.0  # live data intact — only UPSERT writes


# ── the natural key keeps platforms and apps as distinct rows ─────────────────
async def test_platform_and_app_grain_is_distinct(db_session: Any) -> None:
    reg = _load_sync_registry()
    await _setup(db_session, reg)
    for platform, key, rev in [
        ("ios", "appA", 10),
        ("android", "appA", 20),  # same app+date, other platform → distinct row
        ("ios", "appB", 30),
    ]:
        await _insert(
            db_session,
            _STG,
            date=date(2026, 6, 1),
            platform=platform,
            canonical_key=key,
            total_revenue_usd=rev,
        )
    await _upsert(db_session, reg)

    rows = await _fact(db_session)
    assert len(rows) == 3


# ── incremental mode OVERWRITES the rolling window; older history is retained ───
async def _overwrite_window(db: Any, reg: ModuleType, since: date) -> None:
    """Replicates sync_job.merge_and_refresh's incremental path: delete the re-pulled
    window, then reload it from staging (so revised rows update and vanished rows drop)."""
    cols = ", ".join(reg.COLUMN_NAMES)
    await db.execute(text(f"DELETE FROM {_FACT} WHERE date >= :since"), {"since": since})
    await db.execute(text(f"INSERT INTO {_FACT} ({cols}) SELECT {cols} FROM {_STG}"))
    await db.commit()


async def test_incremental_overwrites_window_and_retains_older(db_session: Any) -> None:
    reg = _load_sync_registry()
    await _setup(db_session, reg)
    since = date(2026, 6, 10)
    # Fact: one row BEFORE the window (must survive) + two IN the window.
    await _insert(db_session, _FACT, date=date(2026, 6, 1), platform="ios",
                  canonical_key="old", app_name="Old", total_revenue_usd=10)
    await _insert(db_session, _FACT, date=date(2026, 6, 12), platform="ios",
                  canonical_key="appA", app_name="Stale", total_revenue_usd=1)
    await _insert(db_session, _FACT, date=date(2026, 6, 12), platform="ios",
                  canonical_key="gone", app_name="Vanished", total_revenue_usd=5)
    # Staging = a fresh window pull: appA revised, 'gone' absent, a brand-new row.
    await _insert(db_session, _STG, date=date(2026, 6, 12), platform="ios",
                  canonical_key="appA", app_name="Fresh", total_revenue_usd=777)
    await _insert(db_session, _STG, date=date(2026, 6, 15), platform="android",
                  canonical_key="appB", app_name="New", total_revenue_usd=50)

    await _overwrite_window(db_session, reg, since)

    rows = await _fact(db_session)
    keys = {r.canonical_key for r in rows}
    assert "old" in keys  # older-than-window row RETAINED
    assert "gone" not in keys  # in-window row absent from the fresh pull is REMOVED
    appA = next(r for r in rows if r.canonical_key == "appA")
    assert appA.app_name == "Fresh" and float(appA.total_revenue_usd) == 777.0  # overwritten
    assert "appB" in keys  # new in-window row loaded
    old = next(r for r in rows if r.canonical_key == "old")
    assert float(old.total_revenue_usd) == 10.0  # untouched


# ── staging tolerates duplicate natural keys from the view (no crash), dedupes ──
async def test_staging_dedupes_duplicate_natural_keys(db_session: Any) -> None:
    """A PK-less staging accepts duplicate (date, platform, app_key) rows from the source
    view; generate_dedupe_sql keeps ONE richest row per key before the merge — so the sync
    never crashes on 'duplicate key' and never double-counts."""
    reg = _load_sync_registry()
    for table in (_FACT, _STG):
        await db_session.execute(text(f"DROP TABLE IF EXISTS {table}"))
    await db_session.execute(text(reg.generate_fact_ddl(_FACT)))
    # Staging WITHOUT a primary key — the two duplicate rows below would otherwise crash it.
    await db_session.execute(text(reg.generate_fact_ddl(_STG, with_pk=False)))
    await db_session.commit()

    # Two rows with the SAME natural key (date, platform, canonical_key→app_key) + one distinct.
    await _insert(db_session, _STG, date=date(2026, 6, 24), platform="android",
                  canonical_key="dupapp", app_name="Poor", total_revenue_usd=5,
                  store_total_installs=10)
    await _insert(db_session, _STG, date=date(2026, 6, 24), platform="android",
                  canonical_key="dupapp", app_name="Rich", total_revenue_usd=999,
                  store_total_installs=20)
    await _insert(db_session, _STG, date=date(2026, 6, 24), platform="ios",
                  canonical_key="other", app_name="Solo", total_revenue_usd=1)

    result = await db_session.execute(text(reg.generate_dedupe_sql(_STG)))
    await db_session.commit()
    assert result.rowcount == 1  # exactly one duplicate removed

    kept = (
        await db_session.execute(
            text(f"SELECT canonical_key, app_name, total_revenue_usd FROM {_STG} "
                 f"ORDER BY app_key")
        )
    ).all()
    assert len(kept) == 2
    dup = next(r for r in kept if r.canonical_key == "dupapp")
    assert dup.app_name == "Rich" and float(dup.total_revenue_usd) == 999.0  # richest kept

    # And the deduped staging now UPSERTs cleanly into the live table (no 'affect row twice').
    await _upsert(db_session, reg)
    fact_rows = await _fact(db_session)
    assert len(fact_rows) == 2

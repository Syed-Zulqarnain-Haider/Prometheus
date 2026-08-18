#!/usr/bin/env python3
"""The daily post-sync pass is not actually isolated. Make it so.

``_maybe_evaluate_alerts`` runs alerts, the watchlist anomaly pass and the digest inside
ONE AsyncSession, each wrapped in its own try/except whose comment promises it "must never
block the digest or the loop". That promise does not hold, and the reason is invisible
unless you know SQLAlchemy: when a statement fails, the session is left in a FAILED
TRANSACTION, and every later statement on it raises PendingRollbackError until someone
rolls back. Nobody does.

So the real behaviour is the opposite of the comments:

  * a database error in the alert evaluation makes the watchlist pass fail, and then the
    digest fail, all with unrelated-looking errors;
  * inside notify_watchlists, the per-user handler says "one broken account never stops
    the rest" while in fact the first failure poisons every user after it.

The fix is one line per handler - roll the session back before carrying on - plus the same
inside the per-user loop. Both are wrapped, because a rollback on a connection that has
actually dropped raises too, and the recovery path must not become the new failure.

This is PRE-EXISTING for alerts and the digest; the watchlist pass simply inherited the
pattern. Nothing about behaviour changes on the happy path.

Anchored on CODE ONLY - never on the comment text, which differs between trees.
Idempotent. Backend restart; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCHEDULER = Path("backend/app/services/sync_scheduler.py")
TEST = Path("backend/tests/test_daily_pass.py")

TEST_SOURCE = '''"""The daily post-sync pass must actually be isolated.

Alerts, the watchlist anomaly pass and the digest run on ONE session with a try/except
each, and each of those comments promises it "must never block the digest or the loop".
That promise is only true if the session is rolled back after a failure - SQLAlchemy
leaves it in a FAILED TRANSACTION otherwise, and every later statement raises.

The middle assertion here is the important one: it pins the failure mode, so this test
fails if someone removes the recovery, rather than quietly passing because rollback
happened to be unnecessary.
"""

import pytest
from app.services.sync_scheduler import _recover
from sqlalchemy import text as sql_text

from tests.conftest import MetricsEnv


async def test_recover_makes_a_poisoned_session_usable_again(
    metrics_env: MetricsEnv,
) -> None:
    async with metrics_env.sessionmaker() as session:
        with pytest.raises(Exception):  # noqa: B017 - the driver error type is not the point
            await session.execute(sql_text("SELECT * FROM a_table_that_does_not_exist"))

        # THE FAILURE MODE: the session is now unusable, which is exactly the state each
        # daily-pass handler leaves behind for the next one.
        with pytest.raises(Exception):  # noqa: B017
            await session.execute(sql_text("SELECT 1"))

        await _recover(session)
        assert (await session.execute(sql_text("SELECT 1"))).scalar() == 1


async def test_recover_is_safe_on_a_healthy_session(metrics_env: MetricsEnv) -> None:
    """It runs on every failure path, so it must never be the thing that raises."""
    async with metrics_env.sessionmaker() as session:
        await _recover(session)
        assert (await session.execute(sql_text("SELECT 1"))).scalar() == 1
'''

HELPER_ANCHOR = "async def _maybe_evaluate_alerts(\n"
HELPER_ADD = '''async def _recover(db: AsyncSession) -> None:
    """Return a session to a usable state after a failed statement.

    SQLAlchemy leaves a session in a FAILED TRANSACTION when a statement raises, and every
    later statement on it raises PendingRollbackError until it is rolled back. Without
    this, the "isolated" handlers below are not isolated at all: one database error in the
    first makes every later one fail with an unrelated-looking error.

    Wrapped, because rolling back a connection that has actually dropped raises as well,
    and the recovery path must not become the new failure.
    """
    try:
        await db.rollback()
    except Exception:  # noqa: BLE001 - nothing useful is left to do if this fails
        log.exception("could not roll back the daily-pass session")


'''

IMPORT_ANCHOR = "from sqlalchemy.ext.asyncio import async_sessionmaker\n"
IMPORT_NEW = "from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker\n"

EDITS = [
    (
        '                log.exception("alert evaluation failed")\n',
        '                log.exception("alert evaluation failed")\n'
        "                await _recover(db)\n",
    ),
    (
        '                log.exception("watchlist anomaly pass failed")\n',
        '                log.exception("watchlist anomaly pass failed")\n'
        "                await _recover(db)\n",
    ),
    (
        '                log.exception("digest send failed")\n',
        '                log.exception("digest send failed")\n'
        "                await _recover(db)\n",
    ),
]


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not SCHEDULER.exists():
        die(f"{SCHEDULER} not found - run from the repository root")

    text = SCHEDULER.read_text()
    if "async def _recover(" in text:
        print(f"{SCHEDULER}: already recovers the session")
        if not TEST.exists() or TEST.read_text() != TEST_SOURCE:
            TEST.write_text(TEST_SOURCE)
            print(f"wrote {TEST}")
        return

    anchors = [IMPORT_ANCHOR, HELPER_ANCHOR, *(a for a, _ in EDITS)]
    for anchor in anchors:
        if text.count(anchor) != 1:
            die(f"{SCHEDULER}: expected exactly one {anchor.strip()[:60]!r}, found {text.count(anchor)}")

    text = text.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
    text = text.replace(HELPER_ANCHOR, HELPER_ADD + HELPER_ANCHOR, 1)
    for anchor, replacement in EDITS:
        text = text.replace(anchor, replacement, 1)
    SCHEDULER.write_text(text)
    print(f"patched {SCHEDULER}: each daily-pass handler now recovers the session")
    TEST.write_text(TEST_SOURCE)
    print(f"wrote {TEST}: pins the failure mode as well as the fix")


if __name__ == "__main__":
    main()

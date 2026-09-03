#!/usr/bin/env python3
"""Close the check-then-act races and take exports off the event loop.

FOUR FIXES FROM THE RELIABILITY REVIEW
--------------------------------------
1. LAST-ADMIN RACE (ops #3). Two admins demoting each other concurrently both pass the
   last-admin guard on their pre-commit snapshots, both commits land, zero active admins
   remain - recovery is DB surgery. Not exotic with 8 of 10 accounts holding admin. Admin
   user mutations now take a transaction-scoped advisory lock before the guard reads, so
   the second request blocks until the first commits and then re-reads the truth. The
   lock releases with the transaction; these mutations are rare, so serializing them
   costs nothing anyone will feel.

2. APPROVAL RACE (ops #7). Two admins approving the same pending access request both read
   'pending'; the loser crashes into the unique firebase_uid constraint as a 500 and
   cannot tell the approval actually happened. Deciding a request now locks on the
   request id and RE-READS after acquiring - the loser sees the decision and gets the
   clean "already decided" answer. Reject gets the same treatment: a reject racing an
   approve used to silently overwrite it.

3. FIREBASE COLD-START RACE (ops #8). Two first-ever concurrent requests both find no app
   and both call initialize_app(); the second raises ValueError, which is not
   InvalidTokenError, so a real user got a 500. The loser now checks whether the winner's
   app exists - the outcome both of them wanted.

4. EXPORTS OFF THE EVENT LOOP, AND BOUNDED (ops #9). build_csv/build_xlsx ran inline -
   openpyxl serializing a big workbook stalls every user in the process for the duration
   - and run_report carried no row cap at all. Both builders now run in a worker thread
   (the same pattern token verification already uses) and the report query is capped
   generously (100k rows - no real report approaches it; the cap exists so one runaway
   export cannot occupy the process).

(A fifth item, gating /meta/targets behind a revenue-class metric group, was in the
first version of this script. Recon against the deployed tree shows it already shipped -
the route's docstring now reads "only callers permitted a revenue measure see the
figures" - so it is dropped here rather than applied twice.)

The two database races cannot be exercised by a single-connection test - stated plainly:
they are verified by construction (the lock is the first statement of the transaction,
the re-read happens after acquisition). What IS tested, without a database: the Firebase
init loser accepting the winner's app, the report row cap being real, and both export
builders leaving the event loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
TEST = ROOT / "backend/tests/test_race_hardening.py"

report: list[str] = []

EDITS: list[tuple[str, str, str, str]] = [
    # ── 1. last-admin race ─────────────────────────────────────────────────────
    (
        "backend/app/services/admin_service.py",
        "sqlalchemy text import",
        "from sqlalchemy import and_, delete, func, insert, or_, select",
        "from sqlalchemy import and_, delete, func, insert, or_, select, text",
    ),
    (
        "backend/app/services/admin_service.py",
        "the serializing lock",
        """def is_active_admin(
    *, is_active: bool, roles: list[str], access_expires_at: datetime | None
) -> bool:""",
        '''async def serialize_admin_mutations(db: AsyncSession) -> None:
    """Transaction-scoped advisory lock so admin-management mutations run one at a time.

    Closes a check-then-act race: two admins demoting each other concurrently both pass
    the last-admin guard on their pre-commit snapshots, both commits land, and zero
    active admins remain - recovery is direct DB surgery. The lock is the first
    statement of the transaction and releases with it; admin mutations are rare, so
    serializing them costs nothing anyone will feel.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('prometheus.admin_users'))")
    )


def is_active_admin(
    *, is_active: bool, roles: list[str], access_expires_at: datetime | None
) -> bool:''',
    ),
    (
        "backend/app/api/v1/admin.py",
        "update-user takes the lock before the guard reads",
        """\
    # Last-active-admin lockout guard: refuse any change (demote / deactivate / already-past
    # expiry) that would leave the system with zero active admins. A FUTURE expiry is allowed.
    current_roles = await admin_service.role_names(db, user.id)
    new_is_active = user.is_active if body.is_active is None else body.is_active""",
        """    # Serialize with every other admin mutation BEFORE the guard reads - see
    # serialize_admin_mutations for the two-admins-demote-each-other race this closes.
    await admin_service.serialize_admin_mutations(db)
    # Last-active-admin lockout guard: refuse any change (demote / deactivate / already-past
    # expiry) that would leave the system with zero active admins. A FUTURE expiry is allowed.
    current_roles = await admin_service.role_names(db, user.id)
    new_is_active = user.is_active if body.is_active is None else body.is_active""",
    ),
    (
        "backend/app/api/v1/admin.py",
        "delete-user takes the same lock",
        """    current_roles = await admin_service.role_names(db, user.id)
    if admin_service.is_active_admin(
        is_active=user.is_active, roles=current_roles, access_expires_at=user.access_expires_at
    ) and not await admin_service.other_active_admins_exist(db, user.id):""",
        """    # Same serialization as update: two concurrent deletes must not both pass the
    # last-admin check on stale snapshots.
    await admin_service.serialize_admin_mutations(db)
    current_roles = await admin_service.role_names(db, user.id)
    if admin_service.is_active_admin(
        is_active=user.is_active, roles=current_roles, access_expires_at=user.access_expires_at
    ) and not await admin_service.other_active_admins_exist(db, user.id):""",
    ),
    # ── 2. approval race ───────────────────────────────────────────────────────
    (
        "backend/app/services/access_service.py",
        "sqlalchemy text import",
        "from sqlalchemy import select",
        "from sqlalchemy import select, text",
    ),
    (
        "backend/app/services/access_service.py",
        "approve locks the request and re-reads",
        """    req = await db.get(AccessRequest, request_id)
    if req is None:
        raise LookupError("access request not found")
    if req.status != "pending":
        raise RequestAlreadyDecided(f"request already {req.status}")

    existing = await db.scalar(select(User).where(User.firebase_uid == req.firebase_uid))""",
        """    req = await db.get(AccessRequest, request_id)
    if req is None:
        raise LookupError("access request not found")
    # Serialize concurrent decisions on this request: the loser blocks here until the
    # winner commits, then RE-READS and sees the decision - instead of crashing into the
    # unique firebase_uid constraint as a 500 while the approval had in fact happened.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"access_request:{request_id}"},
    )
    await db.refresh(req)
    if req.status != "pending":
        raise RequestAlreadyDecided(f"request already {req.status}")

    existing = await db.scalar(select(User).where(User.firebase_uid == req.firebase_uid))""",
    ),
    (
        "backend/app/services/access_service.py",
        "reject locks and re-reads too",
        """    req = await db.get(AccessRequest, request_id)
    if req is None:
        raise LookupError("access request not found")
    if req.status != "pending":
        raise RequestAlreadyDecided(f"request already {req.status}")
    req.status = "rejected\"""",
        """    req = await db.get(AccessRequest, request_id)
    if req is None:
        raise LookupError("access request not found")
    # Same serialization as approve: a reject racing an approve used to silently
    # overwrite it - last write won, and nobody was told there was a contest.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"access_request:{request_id}"},
    )
    await db.refresh(req)
    if req.status != "pending":
        raise RequestAlreadyDecided(f"request already {req.status}")
    req.status = "rejected\"""",
    ),
    # ── 3. firebase cold-start race ──────────────────────────────────────────────
    (
        "backend/app/core/security.py",
        "the init race loser accepts the winner's app",
        """        if not firebase_admin._apps:
            firebase_admin.initialize_app()""",
        """        if not firebase_admin._apps:
            try:
                firebase_admin.initialize_app()
            except ValueError:
                # Two cold-start requests race here; the loser finds the app already
                # created by the winner - the outcome both wanted. Any OTHER
                # initialization problem leaves no app and is re-raised.
                if not firebase_admin._apps:
                    raise""",
    ),
    # ── 4. exports: bounded, off the loop ──────────────────────────────────────────
    (
        "backend/app/services/reports_service.py",
        "a generous row cap on report queries",
        """async def run_report(
    session: AsyncSession,
    qb: QueryBuilder,""",
        """# Generous - no real report approaches it. It exists so ONE runaway export (grouped by
# app over years) cannot occupy the process; the UI breakdown route caps at 500 already.
EXPORT_MAX_ROWS = 100_000


async def run_report(
    session: AsyncSession,
    qb: QueryBuilder,""",
    ),
    (
        "backend/app/services/reports_service.py",
        "the cap applied",
        """        stmt = qb.breakdown(filters, group_by, cols)  # type: ignore[arg-type]""",
        """        stmt = qb.breakdown(  # type: ignore[arg-type]
            filters, group_by, cols, limit=EXPORT_MAX_ROWS
        )""",
    ),
    (
        "backend/app/api/v1/export.py",
        "worker-thread import",
        """from fastapi import APIRouter, Depends, HTTPException, Request, status""",
        """import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, status""",
    ),
    (
        "backend/app/api/v1/export.py",
        "CSV builds off the event loop",
        """    if body.format == "csv":
        payload = reports_service.build_csv(result)""",
        """    if body.format == "csv":
        # Serialization is synchronous CPU work; inline it stalled every request in the
        # process for the duration. Same worker-thread pattern token verification uses.
        payload = await anyio.to_thread.run_sync(reports_service.build_csv, result)""",
    ),
    (
        "backend/app/api/v1/export.py",
        "XLSX builds off the event loop",
        """    payload = reports_service.build_xlsx(result)
    return Response(""",
        """    payload = await anyio.to_thread.run_sync(reports_service.build_xlsx, result)
    return Response(""",
    ),
]

TEST_SRC = '''"""The pieces of the race batch that CAN be tested without a second connection.

The two advisory-lock fixes are verified by construction - the lock is the first statement
of the transaction - and pinned here by reading the source, which is a regression guard,
not a proof. The Firebase cold-start race IS proven behaviourally: the loser of the
initialize_app race must accept the winner's app instead of turning a real user into a 500.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from app.api.v1 import admin as admin_routes
from app.api.v1 import export as export_routes
from app.core import security
from app.services import access_service, admin_service, reports_service


# ── 3. the Firebase cold-start race ─────────────────────────────────────────────


def _race(monkeypatch: pytest.MonkeyPatch, *, winner_lands: bool) -> None:
    apps: dict[str, Any] = {}
    monkeypatch.setattr(security.firebase_admin, "_apps", apps, raising=False)

    def initialize_app(*args: Any, **kwargs: Any) -> None:
        if winner_lands:
            apps["[DEFAULT]"] = object()  # the other request got there first
        raise ValueError("The default Firebase app already exists.")

    monkeypatch.setattr(security.firebase_admin, "initialize_app", initialize_app)
    monkeypatch.setattr(security.firebase_auth, "verify_id_token", lambda token: {"uid": "u1"})


def test_the_init_race_loser_accepts_the_winners_app(monkeypatch: pytest.MonkeyPatch) -> None:
    _race(monkeypatch, winner_lands=True)
    claims = security.FirebaseTokenVerifier().verify("token")
    assert claims["uid"] == "u1"


def test_a_real_init_failure_is_still_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    # Same exception type, but nobody created an app: that is a real problem, not a race,
    # and swallowing it would hide a broken deployment behind 401s.
    _race(monkeypatch, winner_lands=False)
    with pytest.raises(ValueError):
        security.FirebaseTokenVerifier().verify("token")


# ── 1 + 2. the advisory locks, by construction ──────────────────────────────────


def test_admin_mutations_take_the_lock_before_the_guard_reads() -> None:
    assert "pg_advisory_xact_lock" in inspect.getsource(admin_service.serialize_admin_mutations)
    src = inspect.getsource(admin_routes)
    guard = src.index("Last-active-admin lockout guard")
    lock = src.index("serialize_admin_mutations(db)")
    assert lock < guard, "the lock must be taken before the last-admin guard reads"
    assert src.count("serialize_admin_mutations(db)") >= 2  # update AND delete


def test_deciding_an_access_request_locks_then_re_reads() -> None:
    for fn in (access_service.approve, access_service.reject):
        src = inspect.getsource(fn)
        assert "pg_advisory_xact_lock" in src, fn.__name__
        assert src.index("pg_advisory_xact_lock") < src.index("request already"), fn.__name__


# ── 4. exports: bounded, and off the event loop ─────────────────────────────────


def test_report_queries_are_capped() -> None:
    assert reports_service.EXPORT_MAX_ROWS == 100_000
    assert "limit=EXPORT_MAX_ROWS" in inspect.getsource(reports_service.run_report)


def test_both_export_builders_leave_the_event_loop() -> None:
    src = inspect.getsource(export_routes)
    assert "anyio.to_thread.run_sync(reports_service.build_csv" in src
    assert "anyio.to_thread.run_sync(reports_service.build_xlsx" in src
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 14)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    marker = ROOT / "backend/app/services/admin_service.py"
    if "serialize_admin_mutations" in marker.read_text():
        print("Already applied - left alone.")
        if TEST.parent.is_dir():
            TEST.write_text(TEST_SRC)
            print(f"  - {TEST}: refreshed")
        return 0

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for rel, label, old, new in EDITS:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"  [{label}] {rel}: file missing")
            continue
        text = planned.get(path, path.read_text())
        if text.count(old) != 1:
            problems.append(
                f"  [{label}] {rel}: expected exactly 1 match, found {text.count(old)}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, new, 1)

    if problems:
        print("NOTHING WAS WRITTEN - locks and guards are all-or-nothing. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for path, text in planned.items():
        path.write_text(text)
        report.append(f"[fix] {path}")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: init race, row cap, exports off the loop")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(
        "\nStated plainly: the two database races are closed by construction (lock first,"
        "\nthen read) and cannot be exercised from a single-connection test. The init race,"
        "\nthe row cap and the worker-thread exports are the tested pieces."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

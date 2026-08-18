#!/usr/bin/env python3
"""Four stale tests, corrected with evidence from an actual run.

Three had been red since before this week - the suite has never run in a deploy, so
nobody saw them. One is mine. None of these corrections weakens an assertion; two make
their test STRONGER.

1. tests/test_admin.py - the targets test asserted that a VIEWER (store_installs only,
   no revenue permission) can read the org's revenue goal, commented "Any authenticated
   user can read targets". That is precisely the disclosure the security audit found and
   the /meta/targets gate closed. The test now asserts BOTH sides: a viewer gets 200 with
   the shape intact and nothing in it, and a role that IS permitted a revenue measure
   still sees the figure. It changes from encoding the leak to guarding against it.

2. tests/test_app_master.py - the refresh response gained a ``new_apps`` key (it drives
   the "new app discovered" admin alert) and the assertion still expected the old
   two-key dict. PRE-EXISTING. The expected dict is completed rather than loosened, so
   the test keeps exact equality.

3. tests/test_migrations.py - ``_HEAD`` pins the expected alembic head so a migration
   cannot land unnoticed. Two have landed since (TOTP schema, then smtp_config), so the
   pin is stale. Deliberately RE-PINNED to the head detected from the migration files at
   patch time, not made dynamic: a literal is the whole point - it forces a human to
   acknowledge each new migration.

4. tests/test_models_metadata.py - EXPECTED_TABLES is an explicit list guarding against
   models appearing by accident. It never learned about chat, announcements or profile
   avatars. PRE-EXISTING; the missing tables are added by name.

Anchored: every anchor must appear the expected number of times or nothing is written.
Idempotent. Tests only - no runtime behaviour, no migration.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ADMIN = Path("backend/tests/test_admin.py")
APP_MASTER = Path("backend/tests/test_app_master.py")
MIGRATIONS = Path("backend/tests/test_migrations.py")
MODELS = Path("backend/tests/test_models_metadata.py")
VERSIONS = Path("backend/alembic/versions")

ADMIN_ANCHOR = '''    # Any authenticated user can read targets for the Overview donut.
    public = await client.get("/api/v1/meta/targets?year=2026", headers=_auth("viewer"))
    assert public.status_code == 200
    assert public.json()["annual"]["target_usd"] == 1_200_000
'''
ADMIN_NEW = '''    # A viewer (store_installs only) must NOT learn the revenue goal. The shape is kept
    # so the Overview donut renders its "target not set" state instead of erroring.
    # Before the gate this endpoint handed the figure to ANY authenticated user - that
    # was the disclosure the security audit found, and this asserts it stays closed.
    public = await client.get("/api/v1/meta/targets?year=2026", headers=_auth("viewer"))
    assert public.status_code == 200
    assert public.json()["annual"] is None
    assert public.json()["monthly"] == []

    # A role that IS permitted a revenue measure still reads the figures here.
    permitted = await client.get("/api/v1/meta/targets?year=2026", headers=_auth("admin"))
    assert permitted.status_code == 200
    assert permitted.json()["annual"]["target_usd"] == 1_200_000
'''

APP_MASTER_ANCHOR = '    assert resp.json() == {"synced": 1, "skipped": 1}\n'
APP_MASTER_NEW = '''    assert resp.json() == {
        "synced": 1,
        "skipped": 1,
        # The refresh also reports apps it had never seen, which drives the "new app
        # discovered" admin alert. Gamma is new in this fixture.
        "new_apps": [{"canonical_key": "app-c", "app_name": "Gamma", "platform": "ios"}],
    }
'''

MIGRATIONS_RE = re.compile(r'^_HEAD = ["\'][0-9a-f]+["\'](.*)$', re.M)

MISSING_TABLES = (
    "conversations",
    "conversation_participants",
    "messages",
    "announcements",
    "user_avatars",
    "smtp_config",
)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def detect_head() -> str:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        for down in re.findall(r"^down_revision[^=]*=\s*(.+)$", text, re.M):
            parents.update(re.findall(r"[\"']([0-9a-f]{8,})[\"']", down))
    heads = revisions - parents
    if len(heads) != 1:
        die(f"expected exactly one migration head, found {len(heads)}: {sorted(heads)}")
    return heads.pop()


def main() -> None:
    for path in (ADMIN, APP_MASTER, MIGRATIONS, MODELS):
        if not path.exists():
            die(f"{path} not found - run from the repository root")
    if not VERSIONS.is_dir():
        die(f"{VERSIONS} not found")

    head = detect_head()
    planned: dict[Path, str] = {}
    skipped: list[str] = []

    # ── VALIDATE EVERYTHING FIRST ──
    # An earlier revision of this script wrote two files and then aborted on the third
    # while printing "Nothing was written" - the exact lie the all-or-nothing rule
    # exists to prevent. Nothing is written until every file has been resolved.
    admin = ADMIN.read_text()
    if 'public.json()["annual"] is None' in admin:
        skipped.append(f"{ADMIN}: already asserts the gate")
    elif admin.count(ADMIN_ANCHOR) != 1:
        die(f"{ADMIN}: expected exactly one public-read block, found {admin.count(ADMIN_ANCHOR)}")
    else:
        planned[ADMIN] = admin.replace(ADMIN_ANCHOR, ADMIN_NEW, 1)

    app_master = APP_MASTER.read_text()
    # Guard on the ANCHOR, not on the string "new_apps": that string appears in OTHER
    # tests in this file, so a marker check reported "already done" and would have
    # skipped the real fix on the tree that needs it.
    if 'assert resp.json() == {\n        "synced": 1,' in app_master:
        skipped.append(f"{APP_MASTER}: already expects new_apps")
    elif app_master.count(APP_MASTER_ANCHOR) != 1:
        die(
            f"{APP_MASTER}: expected exactly one "
            f"{APP_MASTER_ANCHOR.strip()!r}, found {app_master.count(APP_MASTER_ANCHOR)}"
        )
    else:
        planned[APP_MASTER] = app_master.replace(APP_MASTER_ANCHOR, APP_MASTER_NEW, 1)

    migrations = MIGRATIONS.read_text()
    if f'_HEAD = "{head}"' in migrations:
        skipped.append(f"{MIGRATIONS}: already pinned to {head}")
    elif MIGRATIONS_RE.search(migrations) is None:
        die(f"{MIGRATIONS}: no _HEAD pin found")
    else:
        planned[MIGRATIONS] = MIGRATIONS_RE.sub(
            f'_HEAD = "{head}"  # re-pinned; see git log for why', migrations, 1
        )

    models = MODELS.read_text()
    block = re.search(r"EXPECTED_TABLES = \{\n(.*?)\n\}\n", models, re.S)
    if block is None:
        die(f"{MODELS}: EXPECTED_TABLES block not found")
    body = block.group(1)
    missing = [t for t in MISSING_TABLES if f'"{t}"' not in body]
    if not missing:
        skipped.append(f"{MODELS}: already lists every table")
    else:
        additions = "".join(f'    "{t}",\n' for t in missing)
        planned[MODELS] = models.replace(
            block.group(0), f"EXPECTED_TABLES = {{\n{body}\n{additions}}}\n", 1
        )

    # ── WRITE ──
    for line in skipped:
        print(line)
    if not planned:
        print("already corrected - nothing to do")
        return
    for path, text in planned.items():
        path.write_text(text)
        print(f"patched {path}")


if __name__ == "__main__":
    main()

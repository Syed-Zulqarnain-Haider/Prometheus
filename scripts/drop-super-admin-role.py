#!/usr/bin/env python3
"""Remove the super_admin role - the owner asked for it and its related things gone.

WHAT RECON FOUND
----------------
No Python references it any more: admin_service has no SUPER_ADMIN_ROLE, no
guard_target_management, and is_active_admin counts a plain "admin" only. The frontend
has no trace of it either. But the ROW is still there - migration sasuperadmin
(20260821) inserted 'super_admin' into roles, granted it capabilities and metric
permissions, and nothing has ever taken them away.

That is the worst of both worlds: a role that still exists in the database and still
carries grants, with no code enforcing what it was for. Anyone with the admin panel can
assign it, and it would silently confer whatever role_capabilities rows it still holds.

WHY A NEW MIGRATION AND NOT AN EDIT TO THE OLD ONE
--------------------------------------------------
The old migration is in the applied revision chain and another revision already points at
it. Editing history that has run on the deployed database is how you get an environment
that can never be rebuilt from scratch. This adds a new head that undoes it forward.

THE LOCKOUT GUARD
-----------------
Anyone holding ONLY super_admin would lose all access the moment the role is deleted -
which, for the person who created it, means locking the owner out of his own admin panel.
So the migration GRANTS plain admin to every super_admin who does not already have it,
BEFORE removing anything. Belt and braces, and it is idempotent.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(".")
VERSIONS = ROOT / "backend/alembic/versions"
REVISION = "d1c0ff3esuper"


def heads() -> list[str]:
    """Revisions nobody points at - i.e. where a new migration must attach."""
    revs: dict[str, Path] = {}
    downs: set[str] = set()
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text()
        rev = re.search(r"^revision(?::\s*[^=]+)?\s*=\s*[\"']([^\"']+)[\"']", text, re.M)
        if rev:
            revs[rev.group(1)] = path
        for down in re.finditer(
            r"^down_revision(?::\s*[^=]+)?\s*=\s*[\"']([^\"']+)[\"']", text, re.M
        ):
            downs.add(down.group(1))
    return sorted(set(revs) - downs)


MIGRATION = '''"""Remove the super_admin role and everything it still carried.

No code references super_admin any more, but the role row, its capabilities and its
metric permissions were still in the database - a role that grants things with nothing
left to enforce what it meant. Removed here, forward, rather than by editing the
migration that created it (which has already run).

Anyone holding only super_admin is granted plain admin FIRST, so removing the role can
never take away somebody's last way in.

Revision ID: {revision}
Revises: {down}
"""

from __future__ import annotations

from alembic import op

revision: str = "{revision}"
down_revision: str | tuple[str, ...] | None = "{down}"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Nobody loses their last way in. A super_admin without plain admin gets it.
    op.execute(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT ur.user_id, admin_role.id
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        CROSS JOIN (SELECT id FROM roles WHERE name = 'admin') AS admin_role
        WHERE r.name = 'super_admin'
        ON CONFLICT (user_id, role_id) DO NOTHING;
        """
    )
    # 2. Then the grants, the assignments, and the role itself.
    op.execute(
        "DELETE FROM role_capabilities WHERE role_id IN"
        " (SELECT id FROM roles WHERE name = 'super_admin');"
    )
    op.execute(
        "DELETE FROM role_metric_permissions WHERE role_id IN"
        " (SELECT id FROM roles WHERE name = 'super_admin');"
    )
    op.execute(
        "DELETE FROM user_roles WHERE role_id IN"
        " (SELECT id FROM roles WHERE name = 'super_admin');"
    )
    op.execute("DELETE FROM roles WHERE name = 'super_admin';")


def downgrade() -> None:
    # The role comes back empty. Its capabilities and metric permissions are NOT restored:
    # they were granted by a migration that is still in the chain, and re-deriving them
    # here would guess at a state nobody wants back.
    op.execute("INSERT INTO roles (name) VALUES ('super_admin') ON CONFLICT (name) DO NOTHING;")
'''

TEST_SRC = '''"""super_admin is gone, and stays gone.

A role with grants and no code enforcing them is worse than either alone, so this guards
both halves: no source outside the migration chain may name it, and the migration that
removes it must grant plain admin first so it cannot take away somebody's last way in.
"""

from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _sources() -> list[Path]:
    return [
        p
        for p in BACKEND.rglob("*.py")
        if "alembic/versions" not in p.as_posix() and "/tests/" not in p.as_posix()
    ]


def test_no_application_code_mentions_super_admin() -> None:
    offenders = [p.name for p in _sources() if "super_admin" in p.read_text()]
    assert offenders == [], f"super_admin is still referenced in: {offenders}"


def test_the_removal_grants_admin_before_it_deletes_anything() -> None:
    migrations = list((BACKEND / "alembic/versions").glob("*.py"))
    marker = "DELETE FROM roles WHERE name = 'super_admin'"
    removal = [p for p in migrations if marker in p.read_text()]
    assert removal, "no migration removes the super_admin role"
    body = removal[0].read_text()
    grant = body.index("INSERT INTO user_roles")
    delete = body.index("DELETE FROM user_roles")
    assert grant < delete, "the admin grant must come before the role is taken away"
'''


def main() -> int:
    if not VERSIONS.is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    existing = list(VERSIONS.glob("*super_admin*.py")) + list(VERSIONS.glob(f"*{REVISION}*.py"))
    if any(REVISION in p.read_text() for p in VERSIONS.glob("*.py")):
        print("Already applied - left alone.")
        (ROOT / "backend/tests/test_no_super_admin.py").write_text(TEST_SRC)
        print("  - backend/tests/test_no_super_admin.py: refreshed")
        return 0

    found = heads()
    print(f"alembic heads found: {found or '(none)'}")
    if len(found) != 1:
        print(
            "NOTHING WAS WRITTEN - expected exactly one head to attach to."
            " Attaching to the wrong one, or to a branch point, produces a chain that"
            " cannot be upgraded.",
            file=sys.stderr,
        )
        return 1

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
    path = VERSIONS / f"{stamp}_{REVISION}_drop_super_admin_role.py"
    path.write_text(MIGRATION.format(revision=REVISION, down=found[0]))
    (ROOT / "backend/tests/test_no_super_admin.py").write_text(TEST_SRC)

    print("PATCHED, NOT YET VERIFIED - the migration run is the verification.")
    print(f"  - {path}  (down_revision = {found[0]})")
    print("  - backend/tests/test_no_super_admin.py: two cases")
    if existing:
        print("\n  the migration that created it stays in the chain, untouched:")
        for p in existing:
            print(f"    {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

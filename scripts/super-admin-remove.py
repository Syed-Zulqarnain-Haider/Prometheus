#!/usr/bin/env python3
"""Remove super_admin entirely - the role, its guards, its seed rows and its tests.

WHY THIS IS A REVERSAL AND NOT A REWRITE
----------------------------------------
super_admin was installed by scripts/super-admin.py and scripts/fix-super-admin-guards.py,
both of which recorded every change as an exact anchor -> replacement pair. So removal is
not a judgement call about what "related" means: the pairs are run BACKWARDS, and the files
return to the text they held before the role existed. The pairs below were extracted
mechanically from those two installers rather than retyped, so there is nothing here for a
transcription slip to get wrong.

ALL OR NOTHING
--------------
These are authorization guards. A half-applied removal could leave a call to a function
that no longer exists (the app would not start) or, far worse, a guard removed while the
role that it protects survives. So every reversal is checked first, and NOTHING is written
unless all of them match exactly once.

WHAT YOU ARE GIVING UP - SAY IT PLAINLY
---------------------------------------
guard_target_management enforced three rules, and all three go:

  1. a super admin could be changed by nobody but themselves;
  2. a plain admin could be managed only by a super admin;
  3. only a super admin could grant the super-admin role.

Rule 2 is the one with teeth after today: with the guard gone, ANY ADMIN CAN EDIT OR
DELETE ANY OTHER ADMIN. That is exactly how the platform behaved before super_admin was
added, so this is a return to the previous design rather than a new hole - but with 8 of
10 accounts currently holding admin, it is worth knowing rather than discovering.

What does NOT go: the last-active-admin lockout guard. It reverts to counting only
"admin", which is correct once super_admin no longer exists, and it still refuses to let
the final active administrator be removed.

THE DATABASE
------------
The migration promotes any super_admin holder to plain admin FIRST, additively, before
deleting anything. Nobody can be orphaned by this even if somebody was granted the role
between now and the deploy. Then the role's capability, metric-permission and user_roles
rows go, and finally the role itself.

It is deliberately NOT reversible. Recreating the role without its guards would be a role
that grants nothing and protects nothing, which is worse than its absence.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
VERSIONS = ROOT / "backend/alembic/versions"
MIGRATIONS_TEST = ROOT / "backend/tests/test_migrations.py"
SUPER_TEST = ROOT / "backend/tests/test_super_admin.py"
README = ROOT / "README.md"
REVISION = "rmsuperadmin"

report: list[str] = []
skipped: list[str] = []

# (path, text the installer WROTE, text it REPLACED) - applied in reverse.
REVERSALS: list[tuple[str, str, str]] = [
    (
        'backend/app/services/admin_service.py',
        '# ── Super admin: the role that manages admins and that only it can grant ──────────\n# One role sits above admin. It can create and remove admins; a plain admin cannot touch\n# it, cannot grant it, and cannot manage another admin. Every one of these checks lives\n# HERE and is called from the router - never enforced in the UI, which only hides buttons.\nSUPER_ADMIN_ROLE = "super_admin"\n\n\ndef guard_target_management(\n    *,\n    actor_roles: list[str],\n    actor_id: uuid.UUID,\n    target_roles: list[str],\n    target_id: uuid.UUID | None,\n    incoming_roles: list[str] | None = None,\n) -> str | None:\n    """Refusal reason if this actor may NOT manage this target, else None.\n\n    Three rules, in order of strength:\n      1. A super admin is changed by NOBODY but themselves - not another admin, not even\n         another super admin. This is the owner\'s "no one can remove him" made literal.\n      2. A plain admin is managed only by a super admin (or by themselves - editing your\n         own profile is not managing another admin; the last-admin lockout guard is\n         separate and still applies).\n      3. The super-admin role is GRANTED only by a super admin - so nobody can promote\n         themselves or a confederate into it.\n    """\n    actor_is_super = SUPER_ADMIN_ROLE in actor_roles\n    is_self = target_id is not None and target_id == actor_id\n\n    if SUPER_ADMIN_ROLE in target_roles and not is_self:\n        return "A super admin can only be changed by themselves."\n    if "admin" in target_roles and not actor_is_super and not is_self:\n        return "Only a super admin can manage another admin."\n    if incoming_roles is not None and SUPER_ADMIN_ROLE in incoming_roles and not actor_is_super:\n        return "Only a super admin can grant the super-admin role."\n    return None\n\n\ndef is_active_admin(\n    *, is_active: bool, roles: list[str], access_expires_at: datetime | None\n) -> bool:',
        'def is_active_admin(\n    *, is_active: bool, roles: list[str], access_expires_at: datetime | None\n) -> bool:',
    ),
    (
        'backend/app/services/admin_service.py',
        '    not_expired = access_expires_at is None or access_expires_at > datetime.now(UTC)\n    # super_admin counts as admin coverage: a system with a live super admin is never\n    # "orphaned of admins", and the last-admin lockout guard must see it that way.\n    return is_active and ("admin" in roles or SUPER_ADMIN_ROLE in roles) and not_expired',
        '    not_expired = access_expires_at is None or access_expires_at > datetime.now(UTC)\n    return is_active and "admin" in roles and not_expired',
    ),
    (
        'backend/app/services/admin_service.py',
        '        .where(\n            Role.name.in_(("admin", SUPER_ADMIN_ROLE)),\n            User.is_active.is_(True),\n            User.id != exclude_user_id,',
        '        .where(\n            Role.name == "admin",\n            User.is_active.is_(True),\n            User.id != exclude_user_id,',
    ),
    (
        'backend/app/api/v1/admin.py',
        '    current_roles = await admin_service.role_names(db, user.id)\n    refusal = admin_service.guard_target_management(\n        actor_roles=context.roles,\n        actor_id=context.user_id,\n        target_roles=current_roles,\n        target_id=user.id,\n        incoming_roles=body.roles,\n    )\n    if refusal is not None:\n        raise HTTPException(status.HTTP_403_FORBIDDEN, refusal)\n    new_is_active = user.is_active if body.is_active is None else body.is_active',
        '    current_roles = await admin_service.role_names(db, user.id)\n    new_is_active = user.is_active if body.is_active is None else body.is_active',
    ),
    (
        'backend/app/api/v1/admin.py',
        '    current_roles = await admin_service.role_names(db, user.id)\n    refusal = admin_service.guard_target_management(\n        actor_roles=context.roles,\n        actor_id=context.user_id,\n        target_roles=current_roles,\n        target_id=user.id,\n    )\n    if refusal is not None:\n        raise HTTPException(status.HTTP_403_FORBIDDEN, refusal)\n    if admin_service.is_active_admin(',
        '    current_roles = await admin_service.role_names(db, user.id)\n    if admin_service.is_active_admin(',
    ),
    (
        'backend/app/api/v1/admin.py',
        '    _reject_both_expiry(body.access_expires_at, body.access_duration_days)\n    refusal = admin_service.guard_target_management(\n        actor_roles=context.roles,\n        actor_id=context.user_id,\n        target_roles=[],\n        target_id=None,\n        incoming_roles=body.roles,\n    )\n    if refusal is not None:\n        raise HTTPException(status.HTTP_403_FORBIDDEN, refusal)\n    expiry = _resolve_expiry(body.access_expires_at, body.access_duration_days)\n    try:\n        summary = await admin_service.create_user(',
        '    _reject_both_expiry(body.access_expires_at, body.access_duration_days)\n    expiry = _resolve_expiry(body.access_expires_at, body.access_duration_days)\n    try:\n        summary = await admin_service.create_user(',
    ),
    (
        'backend/tests/conftest.py',
        '    "INSERT INTO roles (name) VALUES "\n    "(\'admin\'),(\'super_admin\'),(\'executive\'),(\'pod_owner\'),(\'marketing\'),(\'finance\'),(\'viewer\');"',
        '    "INSERT INTO roles (name) VALUES "\n    "(\'admin\'),(\'executive\'),(\'pod_owner\'),(\'marketing\'),(\'finance\'),(\'viewer\');"',
    ),
    (
        'backend/tests/conftest.py',
        "  WHEN 'admin'     THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']\n  WHEN 'super_admin' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']\n  WHEN 'executive' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']",
        "  WHEN 'admin'     THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']\n  WHEN 'executive' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']",
    ),
    (
        'backend/tests/conftest.py',
        "  WHEN 'admin'     THEN ARRAY['export','share_report','admin_panel']\n  WHEN 'super_admin' THEN ARRAY['export','share_report','admin_panel']",
        "  WHEN 'admin'     THEN ARRAY['export','share_report','admin_panel']",
    ),
    (
        'backend/tests/test_rbac_matrix.py',
        'ROLE_METRIC_GROUPS: dict[str, set[Group]] = {\n    "admin": FULL,\n    # Same DATA access as admin. What sets super_admin apart is structural - who may\n    # manage whom (admin_service.guard_target_management) - not extra metric groups.\n    "super_admin": FULL,',
        'ROLE_METRIC_GROUPS: dict[str, set[Group]] = {\n    "admin": FULL,',
    ),
    (
        'backend/tests/test_rbac_matrix.py',
        'ROLE_CAPABILITIES: dict[str, set[str]] = {\n    "admin": {"export", "share_report", "admin_panel"},\n    "super_admin": {"export", "share_report", "admin_panel"},',
        'ROLE_CAPABILITIES: dict[str, set[str]] = {\n    "admin": {"export", "share_report", "admin_panel"},',
    ),
]


MIGRATION = '''"""Remove the super_admin role.

Revision ID: {rev}
Revises: {down}

The role is withdrawn along with the guards that gave it meaning. Anyone holding it is
given plain admin FIRST, additively, so that removing the role cannot orphan an account -
this runs even though the role is believed to be unheld, because "believed" is not a
safety property and somebody may be granted it before this deploys.

Not reversible on purpose: recreating the role without guard_target_management would be a
role that grants nothing and protects nothing.
"""

from __future__ import annotations

from alembic import op

revision = "{rev}"
down_revision = "{down}"
branch_labels = None
depends_on = None

ROLE = "super_admin"


def upgrade() -> None:
    # 1. Nobody loses access. NOT EXISTS rather than ON CONFLICT so this holds whatever
    #    constraints user_roles happens to carry.
    op.execute(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT ur.user_id, a.id
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        JOIN roles a ON a.name = 'admin'
        WHERE r.name = 'super_admin'
          AND NOT EXISTS (
              SELECT 1 FROM user_roles x
              WHERE x.user_id = ur.user_id AND x.role_id = a.id
          );
        """
    )
    # 2. Then the role's own rows, children before parent.
    for table in ("user_roles", "role_capabilities", "role_metric_permissions"):
        op.execute(
            f"DELETE FROM {{table}} WHERE role_id = "
            "(SELECT id FROM roles WHERE name = 'super_admin');"
        )
    op.execute("DELETE FROM roles WHERE name = 'super_admin';")


def downgrade() -> None:
    """Deliberately empty - see the module docstring."""
'''


def region(path: Path, needle: str, before: int = 4, after: int = 14) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - before), min(len(lines), i + after)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: {needle!r} does not appear"


def single_head() -> str | None:
    """The one revision nothing else builds on. None if that is not a single answer.

    Guessing a parent for a migration is how an alembic graph acquires two heads and the
    next deploy fails somewhere unrelated, so this refuses rather than picks.
    """
    if not VERSIONS.is_dir():
        return None
    revs: dict[str, str | None] = {}
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision\s*=\s*["\']([^"\']+)', text, re.M)
        down = re.search(r'^down_revision\s*=\s*["\']([^"\']+)', text, re.M)
        if rev:
            revs[rev.group(1)] = down.group(1) if down else None
    if not revs:
        return None
    parents = {d for d in revs.values() if d}
    heads = sorted(set(revs) - parents)
    return heads[0] if len(heads) == 1 else None


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    already = not any(
        Path(p).exists() and wrote in Path(p).read_text() for p, wrote, _ in REVERSALS
    )

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for rel, wrote, before in REVERSALS:
        path = Path(rel)
        if not path.exists():
            problems.append(f"  {rel}: file not found")
            continue
        text = planned.get(path, path.read_text())
        if wrote not in text and before in text:
            continue  # this one is already reverted
        found = text.count(wrote)
        if found != 1:
            problems.append(
                f"  {rel}: expected 1 occurrence of the installed text, found {found}\n"
                f"        starts: {wrote.splitlines()[0][:74]!r}"
            )
            continue
        planned[path] = text.replace(wrote, before, 1)

    if problems and not already:
        print("NOTHING WAS WRITTEN. These are authorization guards - a partial removal is")
        print("worse than none, so one mismatch stops the whole thing.\n")
        for line in problems:
            print(line)
        print("\nOn disk:")
        print(region(Path("backend/app/services/admin_service.py"), "guard_target_management"))
        return 1

    for path, text in planned.items():
        # guard_target_management was the only uuid user in admin_service; leaving the
        # import behind would fail lint, and lint failing is the deploy failing.
        if path.name == "admin_service.py" and "uuid." not in text:
            text = re.sub(r"^import uuid\n", "", text, count=1, flags=re.M)
        path.write_text(text)
        report.append(f"[revert] {path}")

    if SUPER_TEST.exists():
        SUPER_TEST.unlink()
        report.append(f"[revert] {SUPER_TEST}: deleted (it tested guards that no longer exist)")

    # ── the database ────────────────────────────────────────────────────────────────
    head = single_head()
    if head is None:
        skipped.append(
            "[db] the alembic graph does not have exactly one head, so no migration was\n"
            "  written - a guessed parent is how a graph acquires two heads and breaks a\n"
            "  later, unrelated deploy. Nothing else was undone; re-run once resolved."
        )
    elif head == REVISION:
        report.append("[db] the removal migration is already the head")
    else:
        target = VERSIONS / f"20260901_0000_{REVISION}_remove_super_admin_role.py"
        target.write_text(MIGRATION.format(rev=REVISION, down=head))
        report.append(f"[db] {target.name}: chains onto {head}")
        if MIGRATIONS_TEST.exists():
            src = MIGRATIONS_TEST.read_text()
            line = re.search(r'^_HEAD\s*=\s*"[^"]*".*$', src, re.M)
            if line:
                new = f'_HEAD = "{REVISION}"  # remove_super_admin_role (current head)'
                MIGRATIONS_TEST.write_text(src[: line.start()] + new + src[line.end() :])
                report.append(f"[db] test_migrations._HEAD -> {REVISION}")
            else:
                skipped.append("[db] no _HEAD assignment in test_migrations.py - check it by hand.")

    # ── the docs ────────────────────────────────────────────────────────────────────
    if README.exists():
        text = README.read_text()
        section = re.search(r"\n#+ [^\n]*super-?admin[^\n]*\n.*?(?=\n#+ |\Z)", text, re.S | re.I)
        if section:
            README.write_text(text[: section.start()] + "\n" + text[section.end() :])
            report.append("[docs] README: the super-administrator section is gone")
        else:
            report.append("[docs] README has no super-admin section - unchanged")

    # ── what is left, said out loud ─────────────────────────────────────────────────
    leftovers: list[str] = []
    for root in (ROOT / "backend/app", ROOT / "backend/tests", ROOT / "frontend"):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            noise = {"node_modules", ".next"} & set(path.parts)
            if path.suffix not in {".py", ".ts", ".tsx"} or noise:
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                # The removal migration's own name contains the word; that is the
                # record of the removal, not a leftover.
                hay = line.replace("remove_super_admin_role", "")
                if any(
                    n in hay
                    for n in ("super_admin", "SUPER_ADMIN", "guard_target_management")
                ):
                    leftovers.append(f"  {path}:{number}  {line.strip()[:110]}")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")

    print("\n" + "=" * 72)
    if leftovers:
        print("STILL MENTIONS super_admin - these were NOT touched, decide on them:")
        for line in leftovers:
            print(line)
    else:
        print("No reference to super_admin, SUPER_ADMIN or guard_target_management remains")
        print("anywhere under backend/app, backend/tests or frontend.")
    print("=" * 72)
    print(
        "\nHEADS UP: with guard_target_management gone, ANY ADMIN CAN EDIT OR DELETE ANY\n"
        "OTHER ADMIN. That is how the platform behaved before super_admin existed, so it\n"
        "is a return to the previous design - but 8 of 10 accounts currently hold admin."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

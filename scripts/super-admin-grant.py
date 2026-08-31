#!/usr/bin/env python3
"""Grant, revoke and inspect super_admin - the one break-glass step the UI cannot do.

WHY A SHELL TOOL AND NOT A BUTTON
---------------------------------
The rule the platform enforces is: super_admin is granted only by a super admin. With
nobody holding it, that rule has no entrance - the role exists with an empty seat and the
admin panel correctly refuses to fill it. That is not a bug; a self-service route to the
top role is a self-service route for an attacker too.

So the seat is filled once, deliberately, from a shell that already has the database. From
then on a super admin manages the rest through the app, where every action is guarded and
audited.

WHAT IT WILL NOT DO
-------------------
  * It will not guess. audit-platform.py promotes "the oldest active admin" as a heuristic;
    that is the wrong shape for handing someone the top role. An email is required and it
    must already exist and be active.
  * It will not revoke the last super admin. The lockout guard the README promises is
    enforced here too, because this tool is precisely the thing that could break it.
  * It does not build SQL from what you typed. The email travels as a psql variable and is
    interpolated with :'email', which quotes it properly. The database credentials stay
    inside the container and never reach the SQL, the argument list, or your shell history.

Every grant and revoke is written to the append-only audit log, with the detail recording
that it came from this shell rather than from a logged-in actor - the one thing that makes
a break-glass tool honest afterwards.

USAGE
    python3 scripts/super-admin-grant.py                  # who holds it, who could
    python3 scripts/super-admin-grant.py --grant  a@b.com
    python3 scripts/super-admin-grant.py --revoke a@b.com
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(".")
COMPOSE = ["docker", "compose", "-f", "docker-compose.prod.yml"]
SEP = "\x1f"  # cannot occur in an email or a timestamp, so a split never chops a value
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RULE = "=" * 72


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def sql(query: str, *, email: str | None = None) -> tuple[list[list[str]], str | None]:
    """Run one statement in the database container. Returns (rows, error).

    ``email`` is passed through the container environment and referenced in the query as
    :'email' - psql does the quoting, so nothing typed at the command line is ever spliced
    into SQL text.
    """
    env = ["-e", f"TARGET_EMAIL={email}"] if email is not None else []
    inner = (
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F"\x1f" -v ON_ERROR_STOP=1 '
        + ('-v email="$TARGET_EMAIL" ' if email is not None else "")
        + "-c "
        + shell_quote(query)
    )
    proc = subprocess.run(
        [*COMPOSE, "exec", "-T", *env, "db", "sh", "-c", inner],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        return [], message.splitlines()[-1] if message else "psql failed"
    rows = [line.split(SEP) for line in proc.stdout.strip().splitlines() if line.strip()]
    return rows, None


def one(query: str, default: str = "", *, email: str | None = None) -> str:
    rows, error = sql(query, email=email)
    if error or not rows or not rows[0]:
        return default
    return rows[0][0]


# ── what the database currently says ───────────────────────────────────────────────

def holders() -> list[list[str]]:
    rows, _ = sql(
        "SELECT u.email, u.is_active::text, coalesce(u.display_name,'') FROM users u "
        "JOIN user_roles ur ON ur.user_id = u.id JOIN roles r ON r.id = ur.role_id "
        "WHERE r.name = 'super_admin' ORDER BY u.email"
    )
    return rows


def admins() -> list[list[str]]:
    rows, _ = sql(
        "SELECT u.email, string_agg(r.name, ',' ORDER BY r.name) FROM users u "
        "JOIN user_roles ur ON ur.user_id = u.id JOIN roles r ON r.id = ur.role_id "
        "WHERE u.is_active GROUP BY u.email "
        "HAVING bool_or(r.name IN ('admin','super_admin')) ORDER BY u.email"
    )
    return rows


def reachable() -> str | None:
    """None if the database answers, otherwise why it did not.

    Kept separate from every other check because "the database is unreachable" and "the
    role is missing" are different problems, and a tool that prints the second sentence for
    the first cause sends you to fix the wrong thing.
    """
    rows, error = sql("SELECT 1")
    if error:
        return error
    return None if rows else "the database answered nothing"


def role_exists() -> bool:
    return one("SELECT count(*) FROM roles WHERE name='super_admin'", "0") != "0"


def user_state(email: str) -> tuple[bool, bool, bool]:
    """(exists, is_active, already_super) for one address."""
    row = one(
        "SELECT u.is_active::text || '|' || (bool_or(r.name='super_admin'))::text "
        "FROM users u LEFT JOIN user_roles ur ON ur.user_id = u.id "
        "LEFT JOIN roles r ON r.id = ur.role_id "
        "WHERE lower(u.email) = lower(:'email') GROUP BY u.is_active",
        email=email,
    )
    if not row:
        return False, False, False
    active, is_super = row.split("|")
    return True, active == "t", is_super == "t"


# ── the append-only record ─────────────────────────────────────────────────────────

def audit(action: str, email: str, detail: dict[str, object]) -> None:
    """Write the grant/revoke to audit_log, using only columns that table actually has.

    A break-glass tool that leaves no trace is how a privilege escalation becomes
    undiscoverable. If the table cannot take the row, that is said out loud rather than
    swallowed - it never blocks the operation itself, which has already happened.
    """
    rows, _ = sql(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='audit_log'"
    )
    if not rows:
        print("  NOTE: no audit_log table found - the change is recorded in user_roles only.")
        return
    columns = {r[0]: r[1] for r in rows}
    payload = json.dumps({**detail, "actor": "shell:super-admin-grant.py"})

    names = ["action"]
    values = [f"'{action}'"]
    if "user_id" in columns:
        # The actor is a shell, not a session. Record the TARGET so the row joins to a
        # real user, and say so in the detail rather than inventing an actor.
        names.append("user_id")
        values.append("(SELECT id FROM users WHERE lower(email)=lower(:'email'))")
    for column, literal in (("resource", "'user'"), ("resource_id", "NULL")):
        if column in columns:
            names.append(column)
            values.append(literal)
    if "detail" in columns:
        names.append("detail")
        values.append(f"{shell_quote(payload)}::jsonb")
    for column in ("ip", "user_agent"):
        if column in columns and columns[column] == "NO":
            names.append(column)
            values.append("'shell'")

    _, error = sql(
        f"INSERT INTO audit_log ({', '.join(names)}) VALUES ({', '.join(values)})",
        email=email,
    )
    if error:
        print(f"  NOTE: the audit row could not be written ({error}).")
    else:
        print(f"  Audited as `{action}`.")


# ── the operations ─────────────────────────────────────────────────────────────────

def show() -> int:
    print(RULE)
    print("SUPER ADMIN")
    print(RULE)
    why = reachable()
    if why is not None:
        print(f"  Cannot reach the database: {why}")
        print("  Nothing was read and nothing was changed. Is the db container up?")
        return 1
    if not role_exists():
        print(
            "  The super_admin ROLE is not in this database. The migration that creates\n"
            "  it has not been applied here - run the deploy before granting anything."
        )
        return 1

    current = holders()
    if current:
        print("  Held by:")
        for email, active, name in current:
            flag = "" if active == "t" else "   [INACTIVE]"
            print(f"    - {email}{(' (' + name + ')') if name else ''}{flag}")
    else:
        print("  Held by: NOBODY.")
        print("    The role exists with an empty seat, so the app has no way to fill it -")
        print("    only a super admin may grant super_admin. That is the bootstrap gap;")
        print("    this tool is the one intended way through it.")

    print("\n  Active accounts with admin-level roles:")
    for email, roles in admins() or [["(none)", ""]]:
        print(f"    - {email:<40} {roles}")

    print("\n  To hand someone the top role:")
    print("    python3 scripts/super-admin-grant.py --grant THEIR_EMAIL")
    return 0


def grant(email: str) -> int:
    why = reachable()
    if why is not None:
        print(f"ABORTED: cannot reach the database ({why}). Nothing changed.", file=sys.stderr)
        return 1
    if not role_exists():
        print("REFUSED: the super_admin role does not exist in this database.", file=sys.stderr)
        return 1
    exists, active, already = user_state(email)
    if not exists:
        print(
            f"REFUSED: no account with the address {email}.\n"
            "  They must sign in once first - the account is created by Firebase login,\n"
            "  not by this tool. Granting the top role to a row that does not exist yet\n"
            "  would either fail or, worse, create a shadow account nobody administers.",
            file=sys.stderr,
        )
        return 1
    if not active:
        print(
            f"REFUSED: {email} exists but is not active.\n"
            "  Re-activate them in the admin panel first, deliberately, then grant.",
            file=sys.stderr,
        )
        return 1
    if already:
        print(f"  {email} already holds super_admin. Nothing to do.")
        return 0

    _, error = sql(
        "INSERT INTO user_roles (user_id, role_id) SELECT u.id, r.id FROM users u, roles r "
        "WHERE lower(u.email) = lower(:'email') AND r.name = 'super_admin' "
        "ON CONFLICT DO NOTHING",
        email=email,
    )
    if error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1

    print(f"  GRANTED super_admin to {email}.")
    print("  Additive - every role the account already had is untouched.")
    audit("super_admin_granted", email, {"target": email, "reason": "bootstrap"})
    print("\n  They must sign out and back in for the new role to appear in their token.")
    return 0


def revoke(email: str) -> int:
    why = reachable()
    if why is not None:
        print(f"ABORTED: cannot reach the database ({why}). Nothing changed.", file=sys.stderr)
        return 1
    exists, _, already = user_state(email)
    if not exists or not already:
        print(f"  {email} does not hold super_admin. Nothing to do.")
        return 0
    if len(holders()) <= 1:
        print(
            f"REFUSED: {email} is the ONLY super admin.\n"
            "  Removing them leaves the role empty and the seat unfillable through the\n"
            "  app again - the same lockout this tool exists to undo. Grant it to someone\n"
            "  else first, then revoke.",
            file=sys.stderr,
        )
        return 1

    _, error = sql(
        "DELETE FROM user_roles WHERE role_id = (SELECT id FROM roles WHERE name='super_admin') "
        "AND user_id = (SELECT id FROM users WHERE lower(email) = lower(:'email'))",
        email=email,
    )
    if error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(f"  REVOKED super_admin from {email}. Their other roles are untouched.")
    audit("super_admin_revoked", email, {"target": email})
    return 0


# ── read-only: can the UI do this without a shell next time? ───────────────────────

def ui_report() -> None:
    """Where the deployed code lists role names, so the follow-up patch has anchors.

    If a hard-coded six-role list drives the admin panel's role picker, then even a real
    super admin cannot grant the role through the app and this shell tool stays the only
    way - which is a gap worth closing, not a design.
    """
    print("\n" + RULE)
    print("READ-ONLY: where role names are hard-coded (nothing was modified)")
    print(RULE)
    needle = re.compile(r"pod_owner|super_admin")
    roots = [ROOT / "backend/app", ROOT / "frontend/components", ROOT / "frontend/lib"]
    seen = 0
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".py", ".ts", ".tsx"} or "node_modules" in path.parts:
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if needle.search(line) and ("viewer" in line or "admin" in line):
                    print(f"  {path}:{number}")
                    print(f"      {line.strip()[:150]}")
                    seen += 1
    if not seen:
        print("  No hard-coded role lists found.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and manage the super_admin role.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--grant", metavar="EMAIL", help="give this account super_admin")
    group.add_argument("--revoke", metavar="EMAIL", help="take super_admin from this account")
    args = parser.parse_args()

    if not (ROOT / "docker-compose.prod.yml").exists():
        print(
            "ABORTED: run this from the deployment directory on the server - it talks to\n"
            "the database through the running db container.",
            file=sys.stderr,
        )
        return 1

    target = args.grant or args.revoke
    if target and not EMAIL_RE.match(target):
        print(f"ABORTED: {target!r} is not an email address.", file=sys.stderr)
        return 1

    if args.grant:
        code = grant(args.grant)
    elif args.revoke:
        code = revoke(args.revoke)
    else:
        code = show()
        ui_report()
        return code

    print()
    show()
    return code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Grant the first super admin, then audit the whole platform and say what is wrong.

WHY SUPER ADMIN IS UNREACHABLE
------------------------------
Nothing is broken. The migration created the role and gave it its permissions, but
promoting the FIRST super admin was deliberately left as a manual step - there is no
self-service bootstrap, on purpose, because a self-service route to the top role is a
self-service route for an attacker too. The step was simply never done, so the role
exists with nobody in it.

This grants it, additively, to the OLDEST ACTIVE ADMIN account - the founding account.
That is a heuristic, so the run prints exactly who was promoted and the one line that
moves it to somebody else. It refuses if a super admin already exists: promoting a
second one silently is not a thing a script should do on its own.

THE AUDIT
---------
Read-only. Everything else here only looks. It checks the things that go wrong quietly -
the ones that show a plausible screen rather than an error: privileges nobody meant to
grant, accounts that should not still be live, data that stopped arriving, a sync that
failed without anyone noticing, settings that silently disable a feature, and the
registry drifting from the code generated out of it.

Findings are ranked. Anything marked FIX is something I will patch; anything marked
DECIDE needs a human to say what the right answer is, because the code cannot know.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(".")
COMPOSE = ["docker", "compose", "-f", "docker-compose.prod.yml"]

findings: list[tuple[str, str, str]] = []  # (severity, area, message)


def note(severity: str, area: str, message: str) -> None:
    findings.append((severity, area, message))


def sql(query: str) -> tuple[list[list[str]], str | None]:
    """Run one query in the database container. Returns (rows, error).

    Values are asked for unaligned and pipe-separated so they parse without a driver;
    the container supplies its own credentials from its environment, so none appear here
    or in anybody's shell history.
    """
    proc = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F"|" -v ON_ERROR_STOP=1 '
            f"-c {shell_quote(query)}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout).strip().splitlines()[-1:][0] if (
            proc.stderr or proc.stdout
        ).strip() else "psql failed"
    rows = [
        line.split("|") for line in proc.stdout.strip().splitlines() if line.strip()
    ]
    return rows, None


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def one(query: str, default: str = "?") -> str:
    rows, error = sql(query)
    if error or not rows:
        return default
    return rows[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 0. Is the database even reachable?
# ─────────────────────────────────────────────────────────────────────────────


def database_reachable() -> bool:
    rows, error = sql("SELECT 1")
    if error:
        print(f"Cannot reach the database: {error}", file=sys.stderr)
        print("Everything below is the code-only half of the audit.\n", file=sys.stderr)
        return False
    return bool(rows)


def tables() -> set[str]:
    rows, _ = sql(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )
    return {r[0] for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# 1. THE FIX: promote the first super admin
# ─────────────────────────────────────────────────────────────────────────────


def promote_super_admin(present: set[str]) -> None:
    print("=" * 72)
    print("SUPER ADMIN")
    print("=" * 72)
    if not {"users", "roles", "user_roles"} <= present:
        note(
            "FIX", "super-admin", "identity tables are missing - cannot promote anyone"
        )
        print("  identity tables missing; skipped.")
        return

    exists = one("SELECT count(*) FROM roles WHERE name='super_admin'", "0")
    if exists == "0":
        note(
            "FIX",
            "super-admin",
            "the super_admin ROLE does not exist - the migration that creates it has "
            "not been applied to this database",
        )
        print("  The super_admin role is not in this database at all.")
        return

    holders, _ = sql(
        "SELECT u.email FROM users u "
        "JOIN user_roles ur ON ur.user_id = u.id "
        "JOIN roles r ON r.id = ur.role_id "
        "WHERE r.name='super_admin' ORDER BY u.email"
    )
    if holders:
        print("  Already held by: " + ", ".join(r[0] for r in holders))
        return

    candidates, _ = sql(
        "SELECT u.email, u.created_at FROM users u "
        "JOIN user_roles ur ON ur.user_id = u.id "
        "JOIN roles r ON r.id = ur.role_id "
        "WHERE r.name='admin' AND u.is_active "
        "AND (u.access_expires_at IS NULL OR u.access_expires_at > now()) "
        "ORDER BY u.created_at ASC LIMIT 1"
    )
    if not candidates:
        note(
            "DECIDE",
            "super-admin",
            "nobody holds an active admin role, so there is no defensible account to "
            "promote automatically",
        )
        print("  No active admin to promote. Nothing done.")
        return

    email = candidates[0][0]
    _, error = sql(
        "INSERT INTO user_roles (user_id, role_id) "
        "SELECT u.id, r.id FROM users u, roles r "
        f"WHERE u.email = '{email}' AND r.name = 'super_admin' "
        "ON CONFLICT DO NOTHING"
    )
    if error:
        note("FIX", "super-admin", f"promotion failed: {error}")
        print(f"  FAILED: {error}")
        return

    print(f"  PROMOTED: {email} (oldest active admin, created {candidates[0][1]})")
    print("  It is additive - the account keeps every role it already had.")
    print("  To move it to somebody else instead, run:")
    print(
        "    docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -U "
        '"$POSTGRES_USER" -d "$POSTGRES_DB" -c "DELETE FROM user_roles WHERE role_id='
        "(SELECT id FROM roles WHERE name=\\'super_admin\\'); INSERT INTO user_roles "
        "(user_id, role_id) SELECT u.id, r.id FROM users u, roles r WHERE "
        "u.email=\\'THEIR_EMAIL\\' AND r.name=\\'super_admin\\';\"'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Who can do what
# ─────────────────────────────────────────────────────────────────────────────


def audit_access(present: set[str]) -> None:
    print("\n" + "=" * 72)
    print("ACCESS")
    print("=" * 72)
    if not {"users", "roles", "user_roles"} <= present:
        return

    rows, _ = sql(
        "SELECT u.email, u.is_active, coalesce(u.access_expires_at::text,''), "
        "coalesce(string_agg(r.name, ',' ORDER BY r.name),'(none)') "
        "FROM users u LEFT JOIN user_roles ur ON ur.user_id=u.id "
        "LEFT JOIN roles r ON r.id=ur.role_id GROUP BY u.id ORDER BY u.email"
    )
    print(f"  {len(rows)} account(s):")
    admins = 0
    for email, active, expires, roles in rows:
        flags = []
        if active != "t":
            flags.append("INACTIVE")
        if expires:
            flags.append(f"expires {expires[:10]}")
        if "admin" in roles.split(","):
            admins += 1
        print(f"    {email:<38} {roles:<28} {' '.join(flags)}")
        if roles == "(none)":
            note(
                "FIX",
                "access",
                f"{email} holds no role at all - it can sign in and see nothing",
            )
        if re.search(r"(^|[^a-z])test|example\.(com|org)|\+test@", email, re.I):
            note(
                "DECIDE",
                "access",
                f"{email} looks like a test account still holding access",
            )
        if active != "t" and "admin" in roles:
            note(
                "DECIDE",
                "access",
                f"{email} is deactivated but still carries the admin role",
            )

    if admins > max(2, len(rows) // 3):
        note(
            "DECIDE",
            "access",
            f"{admins} of {len(rows)} accounts are admins. Admin is not a seniority "
            "badge - every one of them can read every app's numbers and change "
            "anybody's access",
        )

    for role, capability in (("viewer", "export"),):
        held = one(
            "SELECT count(*) FROM role_capabilities rc JOIN roles r ON r.id=rc.role_id "
            f"WHERE r.name='{role}' AND rc.capability='{capability}'",
            "0",
        )
        if held != "0":
            note(
                "FIX",
                "access",
                f"the {role} role can {capability} - that contradicts the spec",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Is the data actually arriving
# ─────────────────────────────────────────────────────────────────────────────


def audit_data(present: set[str]) -> None:
    print("\n" + "=" * 72)
    print("DATA")
    print("=" * 72)

    if "fact_daily_performance" in present:
        row = one(
            "SELECT count(*)||'|'||coalesce(min(date)::text,'-')||'|'||"
            "coalesce(max(date)::text,'-') FROM fact_daily_performance",
            "?|?|?",
        ).split("|")
        print(f"  fact rows: {row[0]}, covering {row[1]} to {row[2]}")
        lag = one(
            "SELECT (current_date - max(date))::text FROM fact_daily_performance", "?"
        )
        if lag.isdigit() and int(lag) > 3:
            note(
                "DECIDE",
                "data",
                f"the newest row is {lag} days old. Apple lags 2-3 days by nature, so "
                "anything beyond that is the sync, not the source",
            )
        unmapped = one(
            "SELECT count(DISTINCT app_key) FROM fact_daily_performance WHERE is_mapped = false",
            "?",
        )
        if unmapped not in ("0", "?"):
            note(
                "DECIDE",
                "data",
                f"{unmapped} app(s) have no App Master entry - what they earn is "
                "attributed to nobody",
            )
        orphan = one(
            "SELECT count(DISTINCT pod) FROM fact_daily_performance WHERE pod = '-1'",
            "?",
        )
        print(f"  unmapped apps: {unmapped}, rows in the Unassigned pod: {orphan}")
    else:
        note("FIX", "data", "fact_daily_performance does not exist")

    if "sync_runs" in present:
        rows, _ = sql(
            "SELECT status, started_at::text, coalesce(rows_loaded::text,'-') "
            "FROM sync_runs ORDER BY started_at DESC LIMIT 5"
        )
        print("  last sync runs:")
        for status, started, loaded in rows:
            print(f"    {started[:19]}  {status:<10} {loaded} rows")
        if rows and rows[0][0].lower() not in ("success", "ok", "succeeded"):
            note(
                "FIX",
                "data",
                f"the most recent sync ended '{rows[0][0]}' - nobody was told",
            )
        failed = one(
            "SELECT count(*) FROM sync_runs WHERE started_at > now() - interval '7 days' "
            "AND lower(status) NOT IN ('success','ok','succeeded')",
            "0",
        )
        if failed not in ("0", "?"):
            note("DECIDE", "data", f"{failed} sync run(s) failed in the last 7 days")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Settings that quietly switch things off
# ─────────────────────────────────────────────────────────────────────────────


def audit_settings(present: set[str]) -> None:
    print("\n" + "=" * 72)
    print("SETTINGS")
    print("=" * 72)
    if "app_settings" not in present:
        print("  (no app_settings table)")
        return
    rows, error = sql("SELECT key, value::text FROM app_settings ORDER BY key")
    if error:
        rows, error = sql("SELECT * FROM app_settings LIMIT 20")
    for row in rows:
        print("    " + "  ".join(row))
    flat = {r[0]: r[1] for r in rows if len(r) >= 2}
    if flat.get("chat_enabled", "").lower() in ("false", "f", "0"):
        note(
            "DECIDE",
            "settings",
            "chat_enabled is off - the assistant is hidden for everyone",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. The append-only promise
# ─────────────────────────────────────────────────────────────────────────────


def audit_audit_log(present: set[str]) -> None:
    print("\n" + "=" * 72)
    print("AUDIT TRAIL")
    print("=" * 72)
    if "audit_log" not in present:
        note("FIX", "audit", "audit_log does not exist")
        return
    count = one("SELECT count(*) FROM audit_log", "?")
    latest = one("SELECT coalesce(max(created_at)::text,'-') FROM audit_log", "?")
    print(f"  {count} entries, most recent {latest[:19]}")
    if count == "0":
        note("FIX", "audit", "the audit log is empty - nothing is being recorded")

    grants, _ = sql(
        "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name='audit_log' AND privilege_type IN ('UPDATE','DELETE') "
        "AND grantee NOT IN ('postgres', current_user)"
    )
    if grants:
        for grantee, privilege in grants:
            note(
                "FIX",
                "audit",
                f"{grantee} can {privilege} audit_log - it is supposed to be append-only",
            )
    else:
        print("  append-only: no role outside the owner holds UPDATE or DELETE")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Code-side checks (no database needed)
# ─────────────────────────────────────────────────────────────────────────────


def audit_code() -> None:
    print("\n" + "=" * 72)
    print("CODE")
    print("=" * 72)

    versions = ROOT / "backend/alembic/versions"
    if versions.is_dir():
        revisions: set[str] = set()
        parents: set[str] = set()
        for path in versions.glob("*.py"):
            source = path.read_text()
            rev = re.search(
                r'^revision(?::[^=\n]+)?\s*=\s*["\']([^"\']+)["\']', source, re.M
            )
            if rev:
                revisions.add(rev.group(1))
            down = re.search(r"^down_revision(?::[^=\n]+)?\s*=\s*(.+)$", source, re.M)
            if down:
                parents.update(re.findall(r'["\']([^"\']+)["\']', down.group(1)))
        heads = sorted(revisions - parents)
        print(f"  {len(revisions)} migrations, head(s): {heads}")
        if len(heads) != 1:
            note(
                "FIX",
                "migrations",
                f"the revision history has {len(heads)} heads: {heads}",
            )

    backend = ROOT / "backend/app/core/metric_registry.py"
    sync = ROOT / "sync/metric_registry.py"
    if backend.exists() and sync.exists():
        names = [
            set(re.findall(r'Col\(\s*"([^"]+)"', p.read_text()))
            for p in (backend, sync)
        ]
        drift = names[0] ^ names[1]
        print(f"  registry: {len(names[0])} columns, sync copy {len(names[1])}")
        if drift:
            note(
                "FIX",
                "registry",
                f"backend and sync registries disagree on: {sorted(drift)}",
            )

    fstring_sql = []
    for path in ROOT.glob("backend/app/**/*.py"):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'(execute|text)\(\s*f["\']', line):
                fstring_sql.append(f"{path}:{i}")
    if fstring_sql:
        print(f"  f-string SQL sites: {len(fstring_sql)}")
        for site in fstring_sql[:10]:
            print(f"    {site}")

    nav = ROOT / "frontend/lib/nav.ts"
    if nav.exists():
        hrefs = set(re.findall(r'href:\s*"(/[^"]*)"', nav.read_text()))
        missing = [
            h
            for h in hrefs
            if not (ROOT / f"frontend/app/(app){h}/page.tsx").exists()
            and not list(ROOT.glob(f"frontend/app/(app){h}/**/page.tsx"))
        ]
        print(f"  nav entries: {len(hrefs)}")
        if missing:
            note("FIX", "routes", f"sidebar links with no page behind them: {missing}")


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    live = database_reachable()
    present = tables() if live else set()

    if live:
        promote_super_admin(present)
        audit_access(present)
        audit_data(present)
        audit_settings(present)
        audit_audit_log(present)
    audit_code()

    print("\n" + "=" * 72)
    print("FINDINGS")
    print("=" * 72)
    if not findings:
        print("  Nothing. Every check passed.")
        return 0
    order = {"FIX": 0, "DECIDE": 1}
    for severity, area, message in sorted(findings, key=lambda f: order.get(f[0], 9)):
        print(f"  [{severity}] {area}: {message}")
    print(
        "\n  FIX    = I will patch these.\n"
        "  DECIDE = needs your answer; the code cannot know what the right one is."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

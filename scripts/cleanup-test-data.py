#!/usr/bin/env python3
"""Remove the test account and everything it owns from production.

The audit found `test@gmail.com` holding a finance role, plus its junk chat messages,
live in production. Test data in a production analytics tool is not cosmetic: it sits in
People lists, pollutes chat, and a test account with a real role is a real credential.

HOW IT DELETES. This does not hard-code the schema. It asks Postgres which tables
reference `users`, and which tables reference THOSE (a chat reaction referencing a
message referencing the user), so whatever exists by the time it runs is found rather
than guessed at. Deletion is innermost-first and one transaction: either the user and
every dependent row go together, or nothing does.

THE AUDIT LOG IS NOT TOUCHED. It is append-only by design and by database grants - this
script must not and cannot delete from it. If audit rows reference the user by FOREIGN
KEY, hard deletion is impossible without breaking that rule, so the script falls back to
NEUTRALIZING the account instead: deactivate it, strip its role, and delete the
dependents that CAN go. History stays; access goes.

DRY RUN FIRST. Without --delete it only prints what it found and what it would do.
Runs inside the backend container so it uses the same DATABASE_URL the app uses:

    docker compose -f docker-compose.prod.yml run --rm -T backend \
        python - --delete < scripts/cleanup-test-data.py
"""

from __future__ import annotations

import os
import sys

TEST_EMAILS = ["test@gmail.com"]
MAX_DEPTH = 4


def main() -> int:
    import psycopg  # available in the backend image via sync/requirements.txt

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ABORTED: DATABASE_URL is not set - run inside the backend container")
        return 1
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    delete = "--delete" in sys.argv

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        # The users table's shape is not assumed either - the first deployment of this
        # script guessed a `role` column and found out the hard way that roles live
        # elsewhere here. Ask the catalog, select what exists.
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'users'"
        )
        user_cols = {r[0] for r in cur.fetchall()}
        if not {"id", "email"} <= user_cols:
            print("ABORTED: users table has no id/email columns - wrong database?")
            return 1
        shown = [c for c in ("id", "email", "role", "is_active") if c in user_cols]
        cur.execute(
            f"SELECT {', '.join(shown)} FROM users WHERE email = ANY(%s)",
            (TEST_EMAILS,),
        )
        found = cur.fetchall()
        if not found:
            print("nothing to do - no test accounts present")
            return 0
        for row in found:
            print("found  " + "  ".join(f"{c}={v}" for c, v in zip(shown, row)))

        # Every FK edge in the schema: (child table, child column, parent table, parent
        # column). Identifiers below come from information_schema, never from any input.
        cur.execute(
            """
            SELECT kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
            """
        )
        edges = cur.fetchall()
        audit_blocked = any(
            child == "audit_log" and parent == "users" for child, _, parent, _ in edges
        )

        def build_plan(table: str, column: str, parent_sql: str, depth: int) -> list:
            """Innermost-first (table, delete_sql, count_sql) steps for rows of `table`
            whose `column` falls inside `parent_sql`. Never enters audit_log."""
            if table == "audit_log" or depth > MAX_DEPTH:
                return []
            steps: list = []
            for child, child_col, parent, parent_col in edges:
                if parent == table and child != table:
                    inner = (
                        f'SELECT "{parent_col}" FROM "{table}" '
                        f'WHERE "{column}" IN ({parent_sql})'
                    )
                    steps += build_plan(child, child_col, inner, depth + 1)
            steps.append(
                (
                    table,
                    f'DELETE FROM "{table}" WHERE "{column}" IN ({parent_sql})',
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IN ({parent_sql})',
                )
            )
            return steps

        ids = [row[0] for row in found]
        user_sql = "SELECT id FROM users WHERE id = ANY(%s)"
        plan: list = []
        planned_tables: set[str] = set()
        for child, child_col, parent, _ in sorted(set(edges)):
            if parent != "users" or child == "audit_log":
                continue
            for step in build_plan(child, child_col, user_sql, 0):
                if step[0] not in planned_tables:
                    planned_tables.add(step[0])
                    plan.append(step)

        for table, _, count_sql in plan:
            cur.execute(count_sql, (ids,))
            count = cur.fetchone()[0]
            if count:
                print(f"  would delete {count:5d} rows from {table}")

        if audit_blocked:
            print()
            print("audit_log holds a FOREIGN KEY to users: the account will be NEUTRALIZED")
            print("(deactivated, role dropped), not hard-deleted - the audit trail is")
            print("append-only and stays intact.")
        if not delete:
            print()
            print("DRY RUN - nothing was changed. Re-run with --delete to apply.")
            return 0

        for table, delete_sql, _ in plan:
            cur.execute(delete_sql, (ids,))
            if cur.rowcount:
                print(f"deleted {cur.rowcount:5d} rows from {table}")
        if audit_blocked:
            sets = [s for s, col in (("is_active = false", "is_active"), ("role = 'viewer'", "role")) if col in user_cols]
            if not sets:
                print("cannot neutralize: users has neither is_active nor role -")
                print("deactivate the account from Admin -> Users instead.")
                conn.commit()
                return 1
            cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ANY(%s)", (ids,))
            print(f"neutralized {cur.rowcount} account(s) via: {', '.join(sets)}")
        else:
            cur.execute("DELETE FROM users WHERE id = ANY(%s)", (ids,))
            print(f"deleted {cur.rowcount} account(s)")
        conn.commit()
        print()
        print("Done, in one transaction. Firebase still holds the auth user - remove")
        print("test@gmail.com in the Firebase console too, or it can sign in again and")
        print("be recreated on first login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

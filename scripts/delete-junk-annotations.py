#!/usr/bin/env python3
"""Delete the test note that a full-platform audit read as TWO different UI bugs.

Chart annotations are dated notes drawn on every daily chart. One junk test note -
"Today is raining cats and dogs.." (2026-08-18, scope: all) - was therefore rendered as
a rotated label on every app-detail chart and read by the audit as a stuck placeholder
string AND a permanently-stuck tooltip. Not a rendering bug; one row of test data,
amplified by a feature doing exactly what it was built to do.

Matches on the phrase, parameterized, and prints every row it touches. Dry run by
default. Deleting via SQL rather than the annotations UI skips the audit log's delete
entry - accepted for a junk test row whose CREATION is already on the audit trail.

    docker compose -f docker-compose.prod.yml run --rm -T backend \
        python - --delete < scripts/delete-junk-annotations.py
"""

from __future__ import annotations

import os
import sys

PHRASE = "%raining cats%"


def main() -> int:
    import psycopg

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ABORTED: DATABASE_URL is not set - run inside the backend container")
        return 1
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    delete = "--delete" in sys.argv

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, annotation_date, note FROM chart_annotations WHERE note ILIKE %s",
            (PHRASE,),
        )
        rows = cur.fetchall()
        if not rows:
            print("nothing to do - no matching notes")
            return 0
        for note_id, day, note in rows:
            print(f"found  {day}  {note[:60]!r}  id={note_id}")
        if not delete:
            print()
            print("DRY RUN - nothing was changed. Re-run with --delete to apply.")
            return 0
        cur.execute("DELETE FROM chart_annotations WHERE note ILIKE %s", (PHRASE,))
        print(f"deleted {cur.rowcount} note(s)")
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())

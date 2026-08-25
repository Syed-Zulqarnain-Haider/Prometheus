#!/usr/bin/env python3
"""Read-only audit of the daily sync and the full backfill.

Answers, with evidence rather than from the code's comments:
  1. Is the deployed sync job the one I have been reading? (checksums)
  2. What window does the DAILY run actually cover, and who sets it?
  3. Has it been running - and succeeding - and how far back does the data go?
  4. Is any of the history older than the daily window now unreachable without a
     manual backfill?
  5. Is the `range` mode (the tool for a historical restatement) reachable from
     the admin UI, or is it code nobody can call?

Writes nothing. Runs no query that is not a SELECT.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = "docker compose -f docker-compose.prod.yml"

# Checksums of the copies these findings were read from. A mismatch means the server is
# running something else and nothing below should be taken on trust.
EXPECTED = {
    "sync/sync_job.py": "1cc2858bc396682b702674d1ecb5db8b",
    "backend/app/services/sync_scheduler.py": "3c4dff0121d55124e761b18146f5e51c",
    "backend/app/services/sync_service.py": "cdfedde8ebcba38bef03366dd8eac8b4",
}


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def run(command: str) -> str:
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=ROOT)
    return (result.stdout or "") + (result.stderr or "")


# ── 1. am I reading the same code that is deployed? ──────────────────────────
rule("1. is the deployed code the code these findings came from?")
for relative, expected in EXPECTED.items():
    path = ROOT / relative
    if not path.exists():
        print(f"  {relative:48} MISSING on this server")
        continue
    digest = hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - identity, not security
    verdict = "same as the copy I read" if digest == expected else "DIFFERENT - re-read it"
    print(f"  {relative:48} {verdict}")

# ── 2. the window the daily run actually uses ────────────────────────────────
rule("2. what the daily run is configured to pull")
print("-- SYNC_* in the compose file (values only; no secrets are printed) --")
compose_file = ROOT / "docker-compose.prod.yml"
if compose_file.exists():
    for number, line in enumerate(compose_file.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"SYNC_|BQ_VIEW|schedule|cron", line, re.I):
            print(f"  {number:4}: {line.strip()}")
else:
    print("  docker-compose.prod.yml not found")

print("\n-- the scheduler: when it fires and with what --")
scheduler = ROOT / "backend" / "app" / "services" / "sync_scheduler.py"
if scheduler.exists():
    for number, line in enumerate(scheduler.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"hour|minute|cron|interval|SYNC_|window|mode|schedule|sleep", line, re.I):
            print(f"  {number:4}: {line.rstrip()}")

print("\n-- the operational settings the admin panel can change --")
print(run("grep -rn 'sync_window\\|sync_mode\\|window_days\\|bq_view' "
          "backend/app/services/settings_service.py backend/app/api/v1/admin.py "
          "2>/dev/null | head -25") or "  (nothing matched)")

# ── 3. is `range` reachable from the UI? ─────────────────────────────────────
rule("3. can an admin run a RANGE sync (the fix for a historical restatement)?")
print(run("grep -rn 'range\\|SYNC_START_DATE\\|SYNC_END_DATE\\|backfill' "
          "backend/app/services/sync_service.py backend/app/api/v1/admin.py "
          "frontend/components/admin 2>/dev/null | head -30") or "  (nothing matched)")

# ── 4. what the database actually shows ──────────────────────────────────────
rule("4. the evidence in the database (read-only)")
PROBE = r'''
import os, re, psycopg

dsn = os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL") or ""
dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", dsn)
if not dsn:
    raise SystemExit("no PG_DSN / DATABASE_URL in the backend environment")

def show(title, sql):
    print("\n-- " + title)
    with psycopg.connect(dsn) as pg, pg.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        print("   " + " | ".join(cols))
        for row in cur.fetchall():
            print("   " + " | ".join("" if v is None else str(v) for v in row))

show("the last 15 sync runs", """
    SELECT id, mode, status, started_at, finished_at, rows_loaded, rows_previous,
           bq_built_at, left(coalesce(error_detail,''), 60) AS error
    FROM sync_runs ORDER BY id DESC LIMIT 15
""")

show("how far back the fact table goes", """
    SELECT min(date) AS earliest, max(date) AS latest,
           count(*) AS rows, count(DISTINCT app_key) AS apps
    FROM fact_daily_performance
""")

show("rows per month (is anything thinning out?)", """
    SELECT date_trunc('month', date)::date AS month, count(*) AS rows,
           count(DISTINCT app_key) AS apps
    FROM fact_daily_performance
    GROUP BY 1 ORDER BY 1 DESC LIMIT 14
""")

show("days inside vs outside the 40-day daily window", """
    SELECT CASE WHEN date >= current_date - 40 THEN 'refreshed daily'
                ELSE 'only a backfill can change it' END AS bucket,
           count(DISTINCT date) AS days, count(*) AS rows
    FROM fact_daily_performance GROUP BY 1
""")

show("any gap in the last 60 days?", """
    SELECT d::date AS missing_day
    FROM generate_series(current_date - 60, current_date, '1 day') d
    WHERE NOT EXISTS (
        SELECT 1 FROM fact_daily_performance f WHERE f.date = d::date
    )
    ORDER BY 1
""")
'''
print(run(f'{COMPOSE} exec -T backend python -c {PROBE!r}'))

print("\nread-only: nothing was written.")

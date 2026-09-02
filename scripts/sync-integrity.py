#!/usr/bin/env python3
"""Sync integrity: the windowed replace can no longer erase history unnoticed.

FOUR FIXES, ONE FILE (applied to sync/sync_job.py and mirrored byte-identical to
backend/sync/sync_job.py - tests/test_sync_vendor_parity.py enforces the mirror).

1. REPLACE GUARD. The incremental/range merge DELETEs the loaded window from the live
   table and reinserts staging. Deliberate (it handles app remapping cleanly), but its
   integrity checks compared BigQuery to a staging table loaded from the same BigQuery
   query - a source missing a week of one channel's partitions passed every check and the
   sync then replaced 40 days of correct history with the broken copy. Now staging is
   compared against the LIVE table it is about to replace, for dates old enough to be
   settled (Apple lags 2-3 days): any settled day about to lose ALL its revenue, or a
   settled window arriving below REPLACE_GUARD_RATIO (default 80%) of live, aborts the
   run - staging discarded, live untouched, alert sent. Exactly the locked failure
   posture. Refund waves fit inside the ratio; losing a channel does not.

2. NaN GATE. Postgres NUMERIC accepts 'NaN' and 'Infinity' verbatim from the COPY, and
   the revenue tolerance check is NaN-blind by IEEE arithmetic (every comparison with NaN
   is false, so "difference > tolerance" never trips). One NaN row makes every dashboard
   SUM() window containing it return NaN. Every registry NUMERIC column is now scanned in
   staging and a non-finite value fails the run at the door.

3. ALERT THAT SURVIVES A DEAD CONNECTION. The crash handler ran pg.rollback() first,
   unguarded - so when the likeliest real crash happened (the DB connection dying
   mid-load), rollback raised on the dead connection and the alert + failure record were
   both lost, leaving a phantom 'running' row. The alert now fires FIRST and never
   touches the database; rollback/record are attempted after, guarded, with the phantom
   possibility logged rather than silent.

4. AUDIT RETENTION SCOPED. Housekeeping's opt-in AUDIT_RETENTION_DAYS pruned every audit
   row uniformly - including admin actions, the rows you want forever. It now prunes only
   the high-volume read-audit actions (api_query, view_page); admin, auth, export and
   sharing history is never touched. (Owner decision from the reliability review: provide
   the mechanism, no automatic deletion - the env var stays opt-in.)

NOT unit-tested here, stated plainly: sync_job.py has no import-safe test harness (it
reads env at import and its tests exercise only the generated SQL), so these paths ride
on the full-suite gate plus the vendor-parity test. A proper harness for sync_job is its
own follow-up - the review flagged sync coverage as thin, and this is that finding.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(".")
CANON = ROOT / "sync/sync_job.py"
VENDOR = ROOT / "backend/sync/sync_job.py"

report: list[str] = []
skipped: list[str] = []

EDITS: list[tuple[str, str, str]] = [
    (
        "import REGISTRY",
        """from metric_registry import (
    COLUMN_NAMES, OPTIONAL_SOURCE_COLUMNS, SOURCE_EXPR, expected_bq_schema,
    generate_fact_ddl, generate_indexes, generate_merge_rows_sql, generate_upsert_sql,
    optional_default_expr,
)""",
        """from metric_registry import (
    COLUMN_NAMES, OPTIONAL_SOURCE_COLUMNS, REGISTRY, SOURCE_EXPR, expected_bq_schema,
    generate_fact_ddl, generate_indexes, generate_merge_rows_sql, generate_upsert_sql,
    optional_default_expr,
)""",
    ),
    (
        "guards above integrity_checks",
        """def integrity_checks(
    bq: bigquery.Client, pg: psycopg.Connection, view: str, rows_loaded: int,""",
        '''# The windowed merge DELETEs the loaded dates from the live table before reinserting.
# Staging arriving materially lighter than what it replaces is not a sync - it is an
# erasure. Recent dates legitimately move (Apple lags 2-3 days), so only dates old enough
# to be settled are compared.
SETTLED_LAG_DAYS = int(os.environ.get("SETTLED_LAG_DAYS", "3"))
REPLACE_GUARD_RATIO = float(os.environ.get("REPLACE_GUARD_RATIO", "0.8"))


def nonfinite_staging_columns(pg: psycopg.Connection) -> list[str]:
    """Registry NUMERIC columns holding NaN/Infinity in staging, as 'name: N row(s)'.

    Postgres NUMERIC accepts 'NaN' and 'Infinity' verbatim from the COPY, and the revenue
    tolerance check is NaN-blind (IEEE: every comparison with NaN is false, so
    "difference > tolerance" never trips). One NaN row poisons every SUM() window that
    contains it, so non-finite values are refused at the door instead.
    """
    cols = [c.name for c in REGISTRY if c.pg_type.upper().startswith("NUMERIC")]
    filters = ", ".join(
        f'COUNT(*) FILTER (WHERE "{c}" = \\'NaN\\'::numeric'
        f' OR "{c}" = \\'Infinity\\'::numeric OR "{c}" = \\'-Infinity\\'::numeric)'
        for c in cols
    )
    with pg.cursor() as cur:
        cur.execute(f"SELECT {filters} FROM {STAGING}")
        counts = cur.fetchone()
    return [f"{name}: {n} row(s)" for name, n in zip(cols, counts) if n]


def replace_guard_problems(
    pg: psycopg.Connection, since: date, until: date | None
) -> list[str]:
    """Refuse a windowed replace that would erase settled history.

    Both checks run against the LIVE table, never BigQuery - comparing the extract to a
    staging table loaded from the same extract is how a broken source passes its own
    inspection. First run (no live table yet) passes: there is nothing to erase.
    """
    problems: list[str] = []
    with pg.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (FACT,))
        if cur.fetchone()[0] is None:
            return problems
        cutoff = date.today() - timedelta(days=SETTLED_LAG_DAYS)
        end = min(until, cutoff) if until is not None else cutoff
        if since > end:
            return problems  # nothing in the window is settled yet
        cur.execute(
            f"SELECT date, COALESCE(SUM(total_revenue_usd), 0) FROM {FACT}"
            " WHERE date >= %s AND date <= %s GROUP BY date", (since, end))
        live = {d: float(v) for d, v in cur.fetchall()}
        cur.execute(
            f"SELECT date, COALESCE(SUM(total_revenue_usd), 0) FROM {STAGING}"
            " WHERE date >= %s AND date <= %s GROUP BY date", (since, end))
        staged = {d: float(v) for d, v in cur.fetchall()}

    # A settled day with live revenue and NO staged revenue is the missing-partition
    # signature: the merge would delete that day and reinsert nothing.
    vanishing = sorted(d for d, v in live.items() if v > 0 and staged.get(d, 0.0) <= 0)
    if vanishing:
        shown = ", ".join(str(d) for d in vanishing[:5])
        more = f" (+{len(vanishing) - 5} more)" if len(vanishing) > 5 else ""
        problems.append(
            f"windowed replace would ERASE {len(vanishing)} settled day(s) that have live"
            f" revenue but no staged revenue: {shown}{more}")

    live_sum, staged_sum = sum(live.values()), sum(staged.values())
    if live_sum > 0 and staged_sum < live_sum * REPLACE_GUARD_RATIO:
        problems.append(
            f"staged revenue for settled dates ({staged_sum:,.2f}) is below"
            f" {REPLACE_GUARD_RATIO:.0%} of live ({live_sum:,.2f}) - refusing to replace"
            " history with a lighter copy")
    return problems


def integrity_checks(
    bq: bigquery.Client, pg: psycopg.Connection, view: str, rows_loaded: int,''',
    ),
    (
        "wire the guards into integrity_checks",
        """    tolerance = max(0.01, abs(float(bq_sum)) * 1e-4)
    if abs(float(bq_sum) - float(pg_sum)) > tolerance:
        problems.append(f"revenue mismatch over window: BQ={bq_sum} PG={pg_sum}")

    return problems""",
        """    tolerance = max(0.01, abs(float(bq_sum)) * 1e-4)
    if abs(float(bq_sum) - float(pg_sum)) > tolerance:
        problems.append(f"revenue mismatch over window: BQ={bq_sum} PG={pg_sum}")

    problems += [f"non-finite values in staging - {p}" for p in nonfinite_staging_columns(pg)]
    # Only windowed modes delete from the live table; a full backfill UPSERTs and cannot
    # erase, so the replace guard applies exactly when since is set.
    if since is not None:
        problems += replace_guard_problems(pg, since, until)

    return problems""",
    ),
    (
        "crash alert survives a dead connection",
        """    except Exception as exc:  # noqa: BLE001
        pg.rollback()
        msg = f"sync crashed - serving yesterday's data. {type(exc).__name__}: {exc}"
        try:
            finish("failed", error=msg[:2000])
        finally:
            alert(msg)
        log.exception("sync crashed")
        return 1""",
        """    except Exception as exc:  # noqa: BLE001
        msg = f"sync crashed - serving yesterday's data. {type(exc).__name__}: {exc}"
        # Alert FIRST, and never through the database: the likeliest real crash is the DB
        # connection dying mid-load, and an alert sequenced after a rollback on that dead
        # connection reports nothing. alert() is already fire-and-forget safe.
        alert(msg)
        try:
            pg.rollback()
            finish("failed", error=msg[:2000])
        except Exception:  # noqa: BLE001
            log.exception(
                "could not record the failure in sync_runs (connection lost?) - the run"
                " may show as 'running' until the stale-run window expires")
        log.exception("sync crashed")
        return 1""",
    ),
    (
        "audit retention keeps admin history forever",
        """                cur.execute(
                    "DELETE FROM audit_log WHERE created_at < now() - make_interval(days => %s)",
                    (int(retention),),
                )""",
        """                cur.execute(
                    "DELETE FROM audit_log"
                    " WHERE created_at < now() - make_interval(days => %s)"
                    " AND action IN ('api_query', 'view_page')",
                    (int(retention),),
                )""",
    ),
    (
        "retention docstring says what it now prunes",
        """\
    1. Optional audit_log retention: if AUDIT_RETENTION_DAYS is set, prune older rows (the
       audit trail is the fastest-growing table - every request is logged).""",
        """    1. Optional audit_log retention: if AUDIT_RETENTION_DAYS is set, prune ONLY the
       high-volume read-audit rows (api_query/view_page - one per dashboard request, the
       fastest-growing rows by far). Admin, auth, export and sharing actions are never
       pruned: those are the rows an investigation needs years later.""",
    ),
]


def window(text: str, needle: str, before: int = 4, after: int = 14) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - before), min(len(lines), i + after)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return "      | (anchor text not found anywhere in the file)"


def main() -> int:
    if not CANON.exists() or not VENDOR.exists():
        print(f"ABORTED: missing {CANON} or {VENDOR}", file=sys.stderr)
        return 1

    text = CANON.read_text()
    if "replace_guard_problems" in text:
        print("Already applied - canonical copy untouched.")
        if VENDOR.read_bytes() != CANON.read_bytes():
            shutil.copyfile(CANON, VENDOR)
            print("  - re-mirrored the vendored copy (was out of parity)")
        return 0

    problems: list[str] = []
    for label, old, _ in EDITS:
        found = text.count(old)
        if found != 1:
            problems.append(f"  [{label}] expected exactly 1 match, found {found}\n"
                            + window(text, old.splitlines()[0].strip()[:60]))
    if problems:
        print("NOTHING WAS WRITTEN - this file feeds the live fact table, so a partial",
              file=sys.stderr)
        print("apply is worse than none. Mismatches:\n", file=sys.stderr)
        for p in problems:
            print(p, file=sys.stderr)
        return 1

    for _, old, new in EDITS:
        text = text.replace(old, new, 1)
    CANON.write_text(text)
    shutil.copyfile(CANON, VENDOR)

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for label, _, _ in EDITS:
        print(f"  - {label}")
    print(f"  - {VENDOR}: mirrored byte-identical (parity test enforces this)")
    print(
        "\nTunables (env, no rebuild): SETTLED_LAG_DAYS=3, REPLACE_GUARD_RATIO=0.8,"
        "\nAUDIT_RETENTION_DAYS stays opt-in and now touches only read-audit rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

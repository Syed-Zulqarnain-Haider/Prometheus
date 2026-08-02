"""
sync_job.py — Daily BigQuery → PostgreSQL sync (Cloud Run Job, ~06:00 UTC via
Cloud Scheduler; Cloud Run retries handle transient failures).

Pipeline (fail-safe at every step — on ANY failure the live table is untouched
and the dashboard keeps serving yesterday's data with a visible freshness banner):

  1. record sync_runs(running)
  2. validate view schema vs metric_registry  → mismatch: 'schema_mismatch', alert, STOP
  3. stream view → fact_daily_performance_staging (COPY, batched)
  4. integrity checks (row delta ±30%, freshness, 7-day revenue penny-match vs BQ)
  5. UPSERT staging → fact_daily_performance by natural key (date, platform, app_key)
     in one transaction — history ACCUMULATES (never a destructive swap/replace)
  6. refresh dim_app, re-grant SELECT to api_service, drop staging
  7. bust Redis 'agg:*' keys
  8. record success + bq_built_at  (the UI's "data as of")

Two modes (SYNC_MODE):
  • 'incremental' (default, the daily job): pull only the last SYNC_WINDOW_DAYS days from the
    view and OVERWRITE that window in Postgres (delete those dates + reload) — so revised
    recent numbers get corrected and rows that disappeared are removed. Older data untouched.
  • 'full' (the on-demand backfill button): pull ALL history and UPSERT/accumulate — never
    deletes anything.

Env vars (all injected from Secret Manager / job config — never hardcoded):
  GCP_PROJECT, BQ_VIEW (default terafort.api.daily_performance_v1),
  PG_DSN (postgresql://sync_service:...@<private-ip>:5432/terafort?sslmode=require),
  SYNC_MODE ('incremental'|'full', default 'incremental'), SYNC_WINDOW_DAYS (default 40),
  REDIS_URL (optional), ALERT_WEBHOOK_URL (optional Slack/Chat webhook)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import sys
import urllib.request
from datetime import date, timedelta

import psycopg
from google.cloud import bigquery

from metric_registry import (
    COLUMN_NAMES, OPTIONAL_SOURCE_COLUMNS, SOURCE_EXPR, expected_bq_schema,
    generate_dedupe_sql, generate_fact_ddl, generate_indexes, generate_upsert_sql,
    optional_default_expr,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync")

FACT = "fact_daily_performance"
STAGING = f"{FACT}_staging"
# Advisory-lock key shared with the backend (app/services/sync_service.py _SYNC_LOCK_KEY)
# so a URL-triggered/scheduled run and an admin "Run Sync Now" can never overlap.
SYNC_ADVISORY_LOCK_KEY = 0x70726F6D  # "prom"
ROW_DELTA_TOLERANCE = 0.30
FRESHNESS_MAX_LAG_DAYS = 3
BATCH_ROWS = 20_000
DEFAULT_WINDOW_DAYS = 40


def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def alert(message: str) -> None:
    """Best-effort alert; never let alerting itself kill the job."""
    log.error("ALERT: %s", message)
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return
    try:
        body = json.dumps({"text": f"[terafort-sync] {message}"}).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:  # noqa: BLE001
        log.exception("Alert webhook failed")


# ── Step 2: schema validation ────────────────────────────────────────────────
def validate_schema(bq: bigquery.Client, view: str) -> tuple[list[str], set[str]]:
    """Return (problems, present_columns). An empty problems list means the load
    may proceed; ``present_columns`` lets the loader default optional-but-absent
    columns (e.g. tech_cost_usd) to 0 rather than failing."""
    project, dataset, name = view.split(".")
    q = f"""
      SELECT column_name, data_type
      FROM `{project}.{dataset}`.INFORMATION_SCHEMA.COLUMNS
      WHERE table_name = @name
    """
    job = bq.query(q, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("name", "STRING", name)]))
    actual = {r.column_name: r.data_type for r in job.result()}
    expected = expected_bq_schema()

    problems: list[str] = []
    for col, typ in expected.items():
        if col not in actual:
            if col in OPTIONAL_SOURCE_COLUMNS:
                # The view hasn't shipped this column yet — load it as 0, don't halt.
                log.warning("optional source column '%s' absent from view; "
                            "defaulting to 0", col)
                continue
            problems.append(f"missing column: {col}")
        elif actual[col] != typ:
            problems.append(f"type changed: {col} expected {typ} got {actual[col]}")
    for col in actual:
        if col not in expected:
            # New, unknown columns are tolerated (warn only): additive view
            # changes don't break us — they just need a registry entry to be used.
            log.warning("View has unregistered column '%s' (ignored until added "
                        "to metric_registry)", col)
    return problems, set(actual)


# Guard for dynamic (BigQuery-discovered) column names before they touch any DDL/SQL.
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def fact_dynamic_columns(pg: psycopg.Connection) -> list[tuple[str, str]]:
    """Active BigQuery-discovered fact columns as ``(name, pg_type)`` from the serving DB,
    or ``[]`` if the ``dynamic_columns`` table doesn't exist yet (fresh DB / pre-migration).

    These were adopted by the admin "Match Database & BigQuery Schema" button; the sync
    loads their values so the columns aren't left NULL. Names are identifier-safe (validated
    on insert by the API and re-checked here)."""
    try:
        with pg.cursor() as cur:
            cur.execute(
                "SELECT name, pg_type FROM dynamic_columns "
                "WHERE table_kind = 'fact' AND active = true ORDER BY id"
            )
            rows = cur.fetchall()
    except psycopg.Error:
        pg.rollback()  # table absent or unreadable — proceed with registry columns only
        return []
    return [(r[0], r[1]) for r in rows if _IDENT_RE.match(r[0])]


# ── Step 3: load into staging ────────────────────────────────────────────────
def _window_sql(since: date | None, until: date | None) -> str:
    """A ``WHERE date …`` clause for the load window (``since``/``until`` are sync-computed
    dates, never user input, so DATE literals are safe). Empty string = full table."""
    conds = []
    if since is not None:
        conds.append(f"date >= '{since.isoformat()}'")
    if until is not None:
        conds.append(f"date <= '{until.isoformat()}'")
    return (" WHERE " + " AND ".join(conds)) if conds else ""


def load_staging(
    bq: bigquery.Client, pg: psycopg.Connection, view: str, present: set[str],
    since: date | None = None, until: date | None = None,
    dyn: list[tuple[str, str]] | None = None,
) -> int:
    """Stream the view into staging. ``since``/``until`` restrict the pull to that date window
    (incremental = rolling window; range = explicit start..end); both ``None`` pulls all.
    ``dyn`` are BigQuery-discovered dynamic columns (name, pg_type) to also load."""
    dyn = dyn or []
    all_cols = [*COLUMN_NAMES, *[n for n, _ in dyn]]
    cols_sql = ", ".join(all_cols)
    with pg.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {STAGING}")
        # Staging has NO primary key: the COPY must never crash on a duplicate natural key
        # from the source view. Duplicates are removed deterministically before the merge
        # (see generate_dedupe_sql), and the LIVE table keeps its PK for the UPSERT.
        cur.execute(generate_fact_ddl(STAGING, with_pk=False))
        # Add the dynamic columns to staging so its shape matches the SELECT + COPY below.
        for name, pg_type in dyn:
            cur.execute(f'ALTER TABLE {STAGING} ADD COLUMN IF NOT EXISTS "{name}" {pg_type}')
    pg.commit()

    # Build the SELECT term for each registry column, in order:
    #   • computed columns (SOURCE_EXPR: pod cast + every derived metric) → their BigQuery
    #     expression aliased to the column name. This is the view's old math, inlined — so
    #     reading the raw source table directly (no view) never drops a derived metric.
    #   • plain columns present in the source → selected by name.
    #   • optional columns the source lacks (e.g. tech_cost_usd) → a type-matched literal
    #     (0 for numerics, typed NULL for text) so the staging shape still lines up.
    # Dynamic columns are selected by name (BigQuery resolves references case-insensitively).
    select_terms = []
    for col in COLUMN_NAMES:
        if col in SOURCE_EXPR:
            select_terms.append(f"{SOURCE_EXPR[col]} AS {col}")
        elif col in present:
            select_terms.append(col)
        else:
            select_terms.append(optional_default_expr(col))
    select_terms += [name for name, _ in dyn]
    rows_iter = bq.query(
        f"SELECT {', '.join(select_terms)} FROM `{view}`{_window_sql(since, until)}"
    ).result(page_size=BATCH_ROWS)

    total = 0
    copy_sql = f"COPY {STAGING} ({cols_sql}) FROM STDIN WITH (FORMAT csv, NULL '\\N')"
    with pg.cursor() as cur, cur.copy(copy_sql) as cp:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in rows_iter:
            writer.writerow(["\\N" if v is None else v for v in row])
            total += 1
            if total % BATCH_ROWS == 0:
                cp.write(buf.getvalue())
                buf.seek(0); buf.truncate(0)
                log.info("loaded %d rows...", total)
        if buf.tell():
            cp.write(buf.getvalue())
    pg.commit()

    with pg.cursor() as cur:
        for ddl in generate_indexes(STAGING, suffix="_s"):
            cur.execute(ddl)
        cur.execute(f"ANALYZE {STAGING}")
    pg.commit()
    return total


# ── Step 4: integrity checks ─────────────────────────────────────────────────
def integrity_checks(
    bq: bigquery.Client, pg: psycopg.Connection, view: str, rows_loaded: int,
    rows_previous: int | None, since: date | None, until: date | None,
    check_freshness: bool,
) -> list[str]:
    problems: list[str] = []

    if rows_loaded == 0:
        return ["staging is empty"]

    if rows_previous and rows_previous > 0:
        delta = abs(rows_loaded - rows_previous) / rows_previous
        if delta > ROW_DELTA_TOLERANCE:
            problems.append(
                f"row count {rows_loaded} deviates {delta:.0%} from previous "
                f"{rows_previous} (tolerance {ROW_DELTA_TOLERANCE:.0%})")

    # Freshness: skipped for an explicit historical range (its data is deliberately old).
    if check_freshness:
        with pg.cursor() as cur:
            cur.execute(f"SELECT MAX(date) FROM {STAGING}")
            max_date: date | None = cur.fetchone()[0]
        if max_date is None or (date.today() - max_date).days > FRESHNESS_MAX_LAG_DAYS:
            problems.append(f"stale data: max(date)={max_date}")

    # Penny-exact revenue match over exactly what we loaded (the window for a windowed load,
    # else the last 7 days for a full backfill) — proves the load fetched every row.
    if since is not None:
        bq_where = _window_sql(since, until)
        pg_where, pg_params = " WHERE date >= %s", [since]
        if until is not None:
            pg_where, pg_params = " WHERE date >= %s AND date <= %s", [since, until]
    else:
        seven = (date.today() - timedelta(days=7)).isoformat()
        bq_where = f" WHERE date >= '{seven}'"
        pg_where, pg_params = " WHERE date >= %s", [seven]
    bq_sum = list(bq.query(
        f"SELECT ROUND(COALESCE(SUM(total_revenue_usd),0),2) FROM `{view}`{bq_where}"
    ).result())[0][0]
    with pg.cursor() as cur:
        cur.execute(
            f"SELECT ROUND(COALESCE(SUM(total_revenue_usd),0),2) FROM {STAGING}{pg_where}",
            tuple(pg_params))
        pg_sum = cur.fetchone()[0]
    # Compare with a tolerance, not strict equality: BQ sums FLOAT64 then rounds, while PG
    # truncates each value to NUMERIC(18,4) on load then sums — so two legitimately-equal
    # loads can differ by a few cents. A small relative epsilon (0.01% of the sum, min 1 cent)
    # avoids spurious aborts (false 'failed' + page) on a good load, while still catching real
    # drift: a dropped/duplicated day moves the window sum by orders of magnitude more.
    tolerance = max(0.01, abs(float(bq_sum)) * 1e-4)
    if abs(float(bq_sum) - float(pg_sum)) > tolerance:
        problems.append(f"revenue mismatch over window: BQ={bq_sum} PG={pg_sum}")

    return problems


# ── Steps 5–6: merge staging into the live fact table + dim_app refresh ───────
def merge_and_refresh(
    pg: psycopg.Connection, mode: str, since: date | None, until: date | None,
    dyn: list[tuple[str, str]] | None = None,
) -> int:
    """Merge the validated staging table into the LIVE fact table, then refresh dim_app.
    Everything runs in ONE transaction — a failure rolls back and leaves live data intact.

    ``full``:                UPSERT by natural key — history accumulates, nothing is deleted.
    ``incremental``/``range``: OVERWRITE the loaded date window — delete those dates in the
                     fact table, then insert the freshly-pulled window. Data outside the window
                     is untouched; rows that vanished from the source within it are removed too.
    ``dyn`` are the BigQuery-discovered dynamic columns loaded into staging this run; they are
    ensured on the live fact table and merged alongside the registry columns."""
    dyn = dyn or []
    dyn_names = [n for n, _ in dyn]
    all_cols = [*COLUMN_NAMES, *dyn_names]
    with pg.cursor() as cur:
        # First run / fresh DB: create the live table + indexes. We NEVER drop or replace
        # the whole table once it exists.
        cur.execute("SELECT to_regclass(%s)", (FACT,))
        if cur.fetchone()[0] is None:
            cur.execute(generate_fact_ddl(FACT))
            for ddl in generate_indexes(FACT):
                cur.execute(ddl)
        # Ensure dynamic columns exist on the live table (reconcile adds them too, but the
        # sync must be self-sufficient so it never inserts into a missing column).
        for name, pg_type in dyn:
            cur.execute(f'ALTER TABLE {FACT} ADD COLUMN IF NOT EXISTS "{name}" {pg_type}')

        # De-duplicate staging on the natural key BEFORE merging (staging has no PK). If the
        # view emitted duplicate (date, platform, app_key) rows, keep one deterministic row
        # each rather than crash the UPSERT ("cannot affect row a second time") or double-count.
        cur.execute(generate_dedupe_sql(STAGING))
        removed = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        if removed:
            log.warning("removed %d duplicate natural-key row(s) from staging", removed)

        if mode in ("incremental", "range") and since is not None:
            # Replace the window atomically: delete the dates we re-pulled, then load the fresh
            # copy. The DELETE bounds match the BigQuery WHERE, so the boundaries align exactly.
            cols_sql = ", ".join(all_cols)
            if until is not None:
                cur.execute(f"DELETE FROM {FACT} WHERE date >= %s AND date <= %s", (since, until))
            else:
                cur.execute(f"DELETE FROM {FACT} WHERE date >= %s", (since,))
            cur.execute(f"INSERT INTO {FACT} ({cols_sql}) SELECT {cols_sql} FROM {STAGING}")
        else:
            # Full backfill: UPSERT by (date, platform, app_key) — existing rows update in
            # place, new dates append, and rows absent from the view are retained.
            cur.execute(generate_upsert_sql(FACT, STAGING, dyn_names))
        cur.execute(f"GRANT SELECT ON {FACT} TO api_service")

        # dim_app: latest mapped attributes per app (read from the now-updated fact)
        cur.execute("DELETE FROM dim_app")
        cur.execute(f"""
            INSERT INTO dim_app (canonical_key, app_name, apple_id, android_package,
                                 ios_bundle_id, publisher, pod, pod_owner, hou,
                                 app_category, ownership_type, is_mapped, updated_at)
            SELECT DISTINCT ON (canonical_key)
                   canonical_key, app_name, apple_id, android_package,
                   ios_bundle_id, publisher, pod, pod_owner, hou,
                   app_category, ownership_type, is_mapped, now()
            FROM {FACT}
            WHERE canonical_key IS NOT NULL
            ORDER BY canonical_key, date DESC
        """)

        # Staging has served its purpose (validation + integrity + the UPSERT source).
        cur.execute(f"DROP TABLE IF EXISTS {STAGING}")
    pg.commit()
    return removed


# ── Step 6.5: housekeeping (reclaim space) ────────────────────────────────────
def housekeeping(pg: psycopg.Connection) -> None:
    """Keep Postgres from bloating. Best-effort — a permission or lock issue must NEVER fail
    the sync (the data is already committed by the time we get here).

    1. Optional audit_log retention: if AUDIT_RETENTION_DAYS is set, prune older rows (the
       audit trail is the fastest-growing table — every request is logged).
    2. VACUUM (ANALYZE) the fact table: the incremental sync deletes + reinserts the recent
       window each run, leaving dead tuples; VACUUM reclaims that space for reuse so the
       table reaches a stable size instead of growing every day.
    """
    retention = os.environ.get("AUDIT_RETENTION_DAYS", "").strip()
    if retention.isdigit() and int(retention) > 0:
        try:
            with pg.cursor() as cur:
                cur.execute(
                    "DELETE FROM audit_log WHERE created_at < now() - make_interval(days => %s)",
                    (int(retention),),
                )
            pg.commit()
            log.info("audit_log pruned to the last %s days", retention)
        except Exception:  # noqa: BLE001
            pg.rollback()
            log.exception("audit_log retention failed (non-fatal)")

    try:
        pg.autocommit = True  # VACUUM cannot run inside a transaction block
        with pg.cursor() as cur:
            cur.execute(f"VACUUM (ANALYZE) {FACT}")
            if retention.isdigit() and int(retention) > 0:
                cur.execute("VACUUM (ANALYZE) audit_log")
        log.info("VACUUM ANALYZE complete")
    except Exception:  # noqa: BLE001
        log.exception("VACUUM failed (non-fatal)")
    finally:
        pg.autocommit = False


# ── Step 7: cache bust ───────────────────────────────────────────────────────
def bust_cache() -> None:
    url = os.environ.get("REDIS_URL")
    if not url:
        log.info("REDIS_URL not set; skipping cache bust")
        return
    try:
        import redis  # imported lazily; optional dependency at runtime
        r = redis.from_url(url, socket_timeout=10)
        deleted = 0
        for key in r.scan_iter("agg:*", count=500):
            r.delete(key); deleted += 1
        log.info("cache bust: deleted %d keys", deleted)
    except Exception:  # noqa: BLE001
        # Cache staleness is bounded by TTL anyway — degrade, don't fail the run.
        log.exception("cache bust failed (non-fatal)")


# ── Orchestration ────────────────────────────────────────────────────────────
def main() -> int:
    project = env("GCP_PROJECT")
    # The sync reads the source table directly (no view). BQ_VIEW is still honored — it's set
    # from the `bq_view` operational setting — but now points at project.dataset.table; the
    # derived metrics the view used to compute are inlined into the load SELECT (SOURCE_EXPR).
    view = env("BQ_VIEW", "terafort.Final_Staging_tables.unified_daily_performance")
    mode = os.environ.get("SYNC_MODE", "incremental").strip().lower()
    if mode not in ("incremental", "full", "range"):
        mode = "incremental"
    try:
        window_days = max(1, int(os.environ.get("SYNC_WINDOW_DAYS", DEFAULT_WINDOW_DAYS)))
    except ValueError:
        window_days = DEFAULT_WINDOW_DAYS

    # Resolve the load window [since, until] (inclusive). full = whole table; incremental =
    # rolling last-N-days; range = an explicit start..end the admin chose.
    since: date | None = None
    until: date | None = None
    if mode == "incremental":
        since = date.today() - timedelta(days=window_days)
    elif mode == "range":
        start_raw = os.environ.get("SYNC_START_DATE", "").strip()
        end_raw = os.environ.get("SYNC_END_DATE", "").strip()
        try:
            since = date.fromisoformat(start_raw) if start_raw else None
            until = date.fromisoformat(end_raw) if end_raw else None
        except ValueError:
            since = until = None
        if since is None:
            log.error("range sync requires a valid SYNC_START_DATE; aborting")
            return 2
        if until is not None and until < since:
            since, until = until, since  # tolerate a swapped range
    log.info("sync mode=%s window_days=%s since=%s until=%s", mode, window_days, since, until)

    bq = bigquery.Client(project=project)
    pg = psycopg.connect(env("PG_DSN"))

    # Self-guard: this job MUST NOT run concurrently with another sync (Cloud Run Jobs run in
    # parallel by default, and the scheduled run can overlap an admin "Run Sync Now"). Two
    # concurrent runs would DROP each other's staging mid-COPY and double-write the live
    # window. A session-level advisory lock makes overlap a clean no-op instead of corruption.
    # Key must match the backend's lock (app/services/sync_service.py SYNC_ADVISORY_LOCK_KEY).
    with pg.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (SYNC_ADVISORY_LOCK_KEY,))
        got_lock = cur.fetchone()[0]
    if not got_lock:
        log.warning("another sync holds the advisory lock — skipping this run (no-op)")
        pg.close()
        return 0

    with pg.cursor() as cur:
        cur.execute("INSERT INTO sync_runs (mode) VALUES (%s) RETURNING id", (mode,))
        run_id = cur.fetchone()[0]
        # Compare row counts against the previous successful run OF THE SAME MODE — a full
        # backfill's count must not be judged against a 40-day incremental's.
        cur.execute("SELECT rows_loaded FROM sync_runs "
                    "WHERE status='success' AND mode=%s ORDER BY id DESC LIMIT 1", (mode,))
        prev = cur.fetchone()
        rows_previous = prev[0] if prev else None
    pg.commit()

    def finish(status: str, *, rows: int | None = None,
               built_at=None, error: str | None = None) -> None:
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE sync_runs SET finished_at=now(), status=%s, rows_loaded=%s,"
                " rows_previous=%s, bq_built_at=%s, error_detail=%s WHERE id=%s",
                (status, rows, rows_previous, built_at, error, run_id))
        pg.commit()

    try:
        problems, present = validate_schema(bq, view)
        if problems:
            msg = "schema mismatch — serving yesterday's data. " + "; ".join(problems)
            finish("schema_mismatch", error=msg); alert(msg)
            return 1

        # BigQuery-discovered dynamic columns adopted by the admin schema-reconcile. Only load
        # ones the view actually still exposes (compared case-insensitively) so a column that
        # vanished before reconcile flagged it can't break the SELECT.
        present_lower = {c.lower() for c in present}
        dyn = [(n, t) for n, t in fact_dynamic_columns(pg) if n in present_lower]
        if dyn:
            log.info("loading %d dynamic column(s): %s", len(dyn), ", ".join(n for n, _ in dyn))

        rows = load_staging(bq, pg, view, present, since=since, until=until, dyn=dyn)
        log.info("staging loaded: %d rows", rows)

        # A row-count delta check needs a comparable baseline; an arbitrary range has none.
        rows_prev_for_check = None if mode == "range" else rows_previous
        problems = integrity_checks(
            bq, pg, view, rows, rows_prev_for_check, since, until,
            check_freshness=(mode != "range"))
        if problems:
            msg = "integrity check failed — serving yesterday's data. " + "; ".join(problems)
            finish("failed", rows=rows, error=msg); alert(msg)
            return 1

        with pg.cursor() as cur:
            cur.execute(f"SELECT MAX(_built_at) FROM {STAGING}")
            built_at = cur.fetchone()[0]

        removed = merge_and_refresh(pg, mode, since, until, dyn=dyn)
        finish("success", rows=rows, built_at=built_at)
        if removed:
            # The run SUCCEEDED (deduped, not crashed); surface the anomaly so the source view
            # can be fixed. Non-fatal — alert is best-effort and never affects the run status.
            alert(
                f"sync succeeded but removed {removed} duplicate natural-key row(s) from "
                f"staging — the view emitted duplicate (date, platform, app_key). Kept the "
                f"richest row per key; investigate the source view."
            )
        housekeeping(pg)  # reclaim space AFTER the run is recorded (best-effort)
        bust_cache()
        log.info("sync complete: %d rows, data as of %s", rows, built_at)
        return 0

    except Exception as exc:  # noqa: BLE001
        pg.rollback()
        msg = f"sync crashed — serving yesterday's data. {type(exc).__name__}: {exc}"
        try:
            finish("failed", error=msg[:2000])
        finally:
            alert(msg)
        log.exception("sync crashed")
        return 1
    finally:
        pg.close()


if __name__ == "__main__":
    sys.exit(main())

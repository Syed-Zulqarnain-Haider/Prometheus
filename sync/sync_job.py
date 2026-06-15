"""
sync_job.py — Daily BigQuery → PostgreSQL sync (Cloud Run Job, ~06:00 UTC via
Cloud Scheduler; Cloud Run retries handle transient failures).

Pipeline (fail-safe at every step — on ANY failure the live table is untouched
and the dashboard keeps serving yesterday's data with a visible freshness banner):

  1. record sync_runs(running)
  2. validate view schema vs metric_registry  → mismatch: 'schema_mismatch', alert, STOP
  3. stream view → fact_daily_performance_staging (COPY, batched)
  4. integrity checks (row delta ±30%, freshness, 7-day revenue penny-match vs BQ)
  5. atomic swap inside one transaction (zero downtime)
  6. refresh dim_app, re-grant SELECT to api_service
  7. bust Redis 'agg:*' keys
  8. record success + bq_built_at  (the UI's "data as of")

Env vars (all injected from Secret Manager / job config — never hardcoded):
  GCP_PROJECT, BQ_VIEW (default terafort.api.daily_performance_v1),
  PG_DSN (postgresql://sync_service:...@<private-ip>:5432/terafort?sslmode=require),
  REDIS_URL (optional), ALERT_WEBHOOK_URL (optional Slack/Chat webhook)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import sys
import urllib.request
from datetime import date, timedelta

import psycopg
from google.cloud import bigquery

from metric_registry import (
    COLUMN_NAMES, INDEX_BASE_NAMES, OPTIONAL_SOURCE_COLUMNS, expected_bq_schema,
    generate_fact_ddl, generate_indexes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync")

FACT = "fact_daily_performance"
STAGING = f"{FACT}_staging"
ROW_DELTA_TOLERANCE = 0.30
FRESHNESS_MAX_LAG_DAYS = 3
BATCH_ROWS = 20_000


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


# ── Step 3: load into staging ────────────────────────────────────────────────
def load_staging(
    bq: bigquery.Client, pg: psycopg.Connection, view: str, present: set[str]
) -> int:
    cols_sql = ", ".join(COLUMN_NAMES)
    with pg.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {STAGING}")
        cur.execute(generate_fact_ddl(STAGING))
    pg.commit()

    # Select every registry column from the view; for optional columns the view
    # doesn't expose yet (e.g. tech_cost_usd) substitute a literal 0 so the column
    # order/shape still matches the staging table.
    select_terms = [
        col if col in present else f"CAST(0 AS FLOAT64) AS {col}"
        for col in COLUMN_NAMES
    ]
    rows_iter = bq.query(f"SELECT {', '.join(select_terms)} FROM `{view}`").result(
        page_size=BATCH_ROWS)

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
def integrity_checks(bq: bigquery.Client, pg: psycopg.Connection,
                     view: str, rows_loaded: int, rows_previous: int | None) -> list[str]:
    problems: list[str] = []

    if rows_loaded == 0:
        return ["staging is empty"]

    if rows_previous and rows_previous > 0:
        delta = abs(rows_loaded - rows_previous) / rows_previous
        if delta > ROW_DELTA_TOLERANCE:
            problems.append(
                f"row count {rows_loaded} deviates {delta:.0%} from previous "
                f"{rows_previous} (tolerance {ROW_DELTA_TOLERANCE:.0%})")

    with pg.cursor() as cur:
        cur.execute(f"SELECT MAX(date) FROM {STAGING}")
        max_date: date | None = cur.fetchone()[0]
    if max_date is None or (date.today() - max_date).days > FRESHNESS_MAX_LAG_DAYS:
        problems.append(f"stale data: max(date)={max_date}")

    # Penny-exact 7-day revenue match between what BQ says and what we loaded.
    since = (date.today() - timedelta(days=7)).isoformat()
    bq_sum = list(bq.query(
        f"SELECT ROUND(COALESCE(SUM(total_revenue_usd),0),2) "
        f"FROM `{view}` WHERE date >= '{since}'").result())[0][0]
    with pg.cursor() as cur:
        cur.execute(f"SELECT ROUND(COALESCE(SUM(total_revenue_usd),0),2) "
                    f"FROM {STAGING} WHERE date >= %s", (since,))
        pg_sum = cur.fetchone()[0]
    if float(bq_sum) != float(pg_sum):
        problems.append(f"7-day revenue mismatch: BQ={bq_sum} PG={pg_sum}")

    return problems


# ── Steps 5–6: atomic swap + dim_app refresh ─────────────────────────────────
def swap_and_refresh(pg: psycopg.Connection) -> None:
    with pg.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (FACT,))
        live_exists = cur.fetchone()[0] is not None

        # One transaction: rename swap is instantaneous; readers never see a gap.
        if live_exists:
            cur.execute(f"ALTER TABLE {FACT} RENAME TO {FACT}_old")
        cur.execute(f"ALTER TABLE {STAGING} RENAME TO {FACT}")
        if live_exists:
            cur.execute(f"DROP TABLE {FACT}_old")   # frees the canonical _pkey name
        cur.execute(f"ALTER TABLE {FACT} RENAME CONSTRAINT {STAGING}_pkey TO {FACT}_pkey")
        for base in INDEX_BASE_NAMES:
            cur.execute(f"ALTER INDEX {base}_s RENAME TO {base}")
        cur.execute(f"GRANT SELECT ON {FACT} TO api_service")

        # dim_app: latest mapped attributes per app
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
    pg.commit()


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
    view = env("BQ_VIEW", "terafort.api.daily_performance_v1")
    bq = bigquery.Client(project=project)
    pg = psycopg.connect(env("PG_DSN"))

    with pg.cursor() as cur:
        cur.execute("INSERT INTO sync_runs DEFAULT VALUES RETURNING id")
        run_id = cur.fetchone()[0]
        cur.execute("SELECT rows_loaded FROM sync_runs "
                    "WHERE status='success' ORDER BY id DESC LIMIT 1")
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

        rows = load_staging(bq, pg, view, present)
        log.info("staging loaded: %d rows", rows)

        problems = integrity_checks(bq, pg, view, rows, rows_previous)
        if problems:
            msg = "integrity check failed — serving yesterday's data. " + "; ".join(problems)
            finish("failed", rows=rows, error=msg); alert(msg)
            return 1

        with pg.cursor() as cur:
            cur.execute(f"SELECT MAX(_built_at) FROM {STAGING}")
            built_at = cur.fetchone()[0]

        swap_and_refresh(pg)
        bust_cache()
        finish("success", rows=rows, built_at=built_at)
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

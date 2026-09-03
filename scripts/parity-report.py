#!/usr/bin/env python3
"""The BigQuery parity report - the second half of the owner's "Both".

Same totals from both ends, side by side: every additive pass-through measure summed over a
date window in the BigQuery view and in the Postgres fact table, with the delta and a
tolerance verdict per column. It answers the question behind "number validation for all of
the numbers" at the only level that is actually provable: does the serving copy match the
source it was loaded from?

It is read-only, admin-only, rate-limited like the other diagnostics, and reuses the
Integration tab's reader key exactly as Test Connection and Schema diff do. The comparison
itself is a pure function with its own tests; the BigQuery call is the one part that cannot
be exercised here and is stated as such.

Everything backend-side lives in a NEW service module - no anchors into integration_service -
so the only edits to existing files are an import, a route, and a schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
SERVICE = ROOT / "backend/app/services/parity_service.py"
TEST = ROOT / "backend/tests/test_parity.py"

SERVICE_SRC = '''"""BigQuery -> Postgres parity: the same totals from both ends, side by side.

Read-only and diagnostic. For a date window, every additive pass-through measure is summed
in the BigQuery view and in the Postgres fact table; each column gets a delta and a
tolerance verdict. Computed columns (those the sync derives) are excluded on purpose - they
do not exist in the source, so there is nothing to compare them against.

The BigQuery half runs in a worker thread with the Integration tab's reader key, exactly
like Test Connection and Schema diff; errors are sanitised to the exception type name.
"""

from __future__ import annotations

import logging
import re
from datetime import date

import anyio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.fact_table import FACT_TABLE
from app.schemas.integration import ParityReport, ParityRow
from app.services import query_builder
from app.services.integration_service import _BQ_SCOPES, _bq_key_present

log = logging.getLogger(__name__)

TOLERANCE = 0.005  # half a percent, relative to the larger side
MAX_SPAN_DAYS = 92
_IDENT = re.compile(r"^[A-Za-z0-9_-]+$")


def parity_columns() -> list[str]:
    """Additive measures that exist in the SOURCE - the effective registry minus anything
    the sync computes itself."""
    return sorted(
        name for name, col in query_builder.additive_measures().items() if col.source_expr is None
    )


def split_view(gcp_project: str, bq_view: str) -> tuple[str, str, str] | None:
    """``project.dataset.table`` or ``dataset.table`` (project from settings). None if the
    reference is not three safe identifiers - these are interpolated into the query."""
    parts = bq_view.strip().split(".")
    if len(parts) == 2:
        parts = [gcp_project.strip(), *parts]
    if len(parts) != 3 or not all(_IDENT.match(p) for p in parts):
        return None
    return parts[0], parts[1], parts[2]


def compare_totals(
    bigquery: dict[str, float], postgres: dict[str, float], tolerance: float = TOLERANCE
) -> list[ParityRow]:
    """Pure. One row per column present on either side; a column missing from one side
    counts as zero there, which surfaces as a mismatch rather than hiding."""
    rows: list[ParityRow] = []
    for column in sorted(set(bigquery) | set(postgres)):
        bq = float(bigquery.get(column) or 0.0)
        pg = float(postgres.get(column) or 0.0)
        delta = pg - bq
        scale = max(abs(bq), abs(pg))
        within = scale == 0.0 or abs(delta) <= tolerance * scale
        pct = None if bq == 0.0 else delta / abs(bq)
        rows.append(
            ParityRow(
                column=column,
                bigquery=bq,
                postgres=pg,
                delta=delta,
                delta_pct=pct,
                within_tolerance=within,
            )
        )
    return rows


def validate_window(date_from: str, date_to: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    except ValueError as exc:
        raise ValueError("dates must be ISO yyyy-mm-dd") from exc
    if start > end:
        raise ValueError("date_from must be on or before date_to")
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        raise ValueError(f"window too large: max {MAX_SPAN_DAYS} days")
    return start, end


def _run_bq_totals(
    key_path: str,
    project: str,
    dataset: str,
    table: str,
    columns: list[str],
    start: date,
    end: date,
) -> tuple[dict[str, float] | None, str | None]:
    """Synchronous; runs in a worker thread. Identifiers come from the registry and a
    validated view reference, never from the caller; dates go in as query parameters."""
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except Exception:  # noqa: BLE001
        return (None, "BigQuery client library is not available in this environment.")
    try:
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=_BQ_SCOPES
        )
        client = bigquery.Client(project=project, credentials=credentials)
        selects = ", ".join(f"SUM(`{c}`) AS `{c}`" for c in columns)
        query = (
            f"SELECT {selects} FROM `{project}.{dataset}.{table}` "
            "WHERE date BETWEEN @date_from AND @date_to"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("date_from", "DATE", start),
                bigquery.ScalarQueryParameter("date_to", "DATE", end),
            ],
            use_query_cache=False,
        )
        row = next(iter(client.query(query, job_config=job_config, timeout=60).result()))
        return ({c: float(row[c] or 0.0) for c in columns}, None)
    except Exception as exc:  # noqa: BLE001 - sanitise: type name only, never the message
        log.warning("parity query failed: %s", type(exc).__name__)
        return (None, f"Parity query failed ({type(exc).__name__}).")


async def postgres_totals(
    db: AsyncSession, columns: list[str], start: date, end: date
) -> dict[str, float]:
    present = [c for c in columns if c in FACT_TABLE.c]
    if not present:
        return {}
    stmt = select(
        *[func.coalesce(func.sum(FACT_TABLE.c[c]), 0).label(c) for c in present]
    ).where(FACT_TABLE.c.date >= start, FACT_TABLE.c.date <= end)
    row = (await db.execute(stmt)).mappings().one()
    return {c: float(row[c] or 0.0) for c in present}


async def parity_report(
    db: AsyncSession,
    settings: Settings,
    gcp_project: str,
    bq_view: str,
    date_from: str,
    date_to: str,
) -> ParityReport:
    start, end = validate_window(date_from, date_to)

    def report(**fields: object) -> ParityReport:
        # Every outcome carries the window it was asked about, so a "not configured" or a
        # failure is still attributable to a specific range in the UI and the audit trail.
        return ParityReport.model_validate(
            {
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
                "tolerance": TOLERANCE,
                **fields,
            }
        )

    if not _bq_key_present(settings):
        return report(
            configured=False,
            message="No BigQuery reader key mounted - set BQ_CREDENTIALS_PATH and mount the key.",
        )
    ref = split_view(gcp_project, bq_view)
    if ref is None:
        return report(
            configured=True, message="The configured BigQuery view reference is not valid."
        )
    columns = parity_columns()
    bq, error = await anyio.to_thread.run_sync(
        _run_bq_totals, settings.bq_credentials_path, *ref, columns, start, end
    )
    if bq is None:
        return report(configured=True, message=error or "Parity query failed.")
    pg = await postgres_totals(db, columns, start, end)
    rows = compare_totals(bq, pg)
    mismatched = [r.column for r in rows if not r.within_tolerance]
    return report(configured=True, in_sync=not mismatched, rows=rows, mismatched=mismatched)
'''

TEST_SRC = '''"""Parity: the comparison is pure and provable; the BigQuery call is not exercised here.

Stated plainly: nothing in this file talks to BigQuery. What is tested is everything around
it - the window validation, the view reference parsing, the not-configured path, and the
comparison itself, which is where a wrong verdict would actually come from.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.core.config import get_settings
from app.services import parity_service
from app.services.parity_service import compare_totals, split_view, validate_window


def test_identical_totals_are_in_tolerance() -> None:
    rows = compare_totals({"a": 100.0, "b": 0.0}, {"a": 100.0, "b": 0.0})
    assert all(r.within_tolerance for r in rows)
    assert [r.column for r in rows] == ["a", "b"]


def test_a_small_relative_drift_is_tolerated_and_a_large_one_is_not() -> None:
    fine, bad = compare_totals({"x": 1000.0, "y": 1000.0}, {"x": 1004.0, "y": 1100.0})
    assert fine.within_tolerance and fine.delta == 4.0
    assert not bad.within_tolerance and bad.delta_pct == pytest.approx(0.1)


def test_a_column_missing_on_one_side_is_a_mismatch_not_a_silence() -> None:
    (row,) = compare_totals({"only_in_bq": 50.0}, {})
    assert row.postgres == 0.0 and not row.within_tolerance
    (row,) = compare_totals({}, {"only_in_pg": 50.0})
    assert row.bigquery == 0.0 and row.delta_pct is None and not row.within_tolerance


def test_the_view_reference_is_three_safe_identifiers() -> None:
    assert split_view("proj", "terafort.api.daily_performance_v1") == (
        "terafort",
        "api",
        "daily_performance_v1",
    )
    assert split_view("proj", "api.daily_performance_v1") == ("proj", "api", "daily_performance_v1")
    assert split_view("proj", "api.daily_performance_v1; DROP TABLE x") is None
    assert split_view("proj", "one_part") is None


def test_the_window_is_validated_before_anything_is_queried() -> None:
    with pytest.raises(ValueError):
        validate_window("2026-02-01", "2026-01-01")
    with pytest.raises(ValueError):
        validate_window("2026-01-01", "2026-12-31")
    with pytest.raises(ValueError):
        validate_window("yesterday", "today")
    assert validate_window("2026-01-01", "2026-01-31")[1].day == 31


async def test_without_a_reader_key_the_report_says_so_and_touches_nothing() -> None:
    settings = get_settings().model_copy(update={"bq_credentials_path": "/nonexistent/key.json"})
    db: Any = None  # must not be touched on this path
    report = await parity_service.parity_report(
        db, settings, "proj", "api.view", "2026-01-01", "2026-01-07"
    )
    assert report.configured is False and report.in_sync is False and report.rows == []


def test_computed_columns_are_never_compared() -> None:
    # They are produced by the sync, so they do not exist in the source view.
    cols = set(parity_service.parity_columns())
    from app.core.metric_registry import REGISTRY

    assert not any(c.name in cols for c in REGISTRY if c.source_expr is not None)
'''

SCHEMA_SRC = '''class ParityRow(BaseModel):
    """One column's totals from both ends, for a date window."""

    column: str
    bigquery: float
    postgres: float
    delta: float  # postgres - bigquery
    delta_pct: float | None = None  # relative to BigQuery; None when BigQuery is zero
    within_tolerance: bool


class ParityReport(BaseModel):
    """BigQuery vs Postgres totals over a window - proof the serving copy matches its source.

    Read-only and diagnostic. ``in_sync`` means every compared column is within tolerance.
    """

    configured: bool
    in_sync: bool = False
    message: str | None = None  # sanitized note (not-configured / read failure)
    date_from: str | None = None
    date_to: str | None = None
    tolerance: float = 0.005
    rows: list[ParityRow] = []
    mismatched: list[str] = []


'''

ROUTE_SRC = '''# ── Integration: BigQuery -> Postgres parity (read-only, diagnostic) ──────────────────
@router.get(
    "/integration/parity",
    response_model=ParityReport,
    dependencies=[Depends(enforce_diagnostics_rate_limit)],
)
async def get_parity_report(db: DbSession, date_from: str, date_to: str) -> ParityReport:
    """Sum every additive pass-through measure over the window in BOTH the BigQuery view and
    the Postgres fact table and report the deltas. READ-ONLY; uses the reader key."""
    settings = get_settings()
    gcp_project = str(await settings_service.get_value(db, "gcp_project"))
    bq_view = str(await settings_service.get_value(db, "bq_view"))
    try:
        return await parity_service.parity_report(
            db, settings, gcp_project, bq_view, date_from, date_to
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


'''

TS_TYPES = '''export interface ParityRow {
  column: string;
  bigquery: number;
  postgres: number;
  delta: number;
  delta_pct: number | null;
  within_tolerance: boolean;
}
export interface ParityReport {
  configured: boolean;
  in_sync: boolean;
  message: string | null;
  date_from: string | null;
  date_to: string | null;
  tolerance: number;
  rows: ParityRow[];
  mismatched: string[];
}
'''

TS_HOOK = '''
export function useParityReport() {
  return useMutation({
    mutationFn: (range: { from: string; to: string }) =>
      apiFetch<ParityReport>(
        `/api/v1/admin/integration/parity?date_from=${range.from}&date_to=${range.to}`,
      ),
  });
}
'''

PANEL_SECTION = '''function ParitySection() {
  const parity = useParityReport();
  // Default to a settled week: Apple lags 2-3 days, so end three days back.
  const end = new Date();
  end.setDate(end.getDate() - 3);
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const [from, setFrom] = useState(iso(start));
  const [to, setTo] = useState(iso(end));
  const report = parity.data;

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        Parity check
      </h2>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">BigQuery vs Postgres totals</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Sums every additive measure over the window in the BigQuery view and in the
            serving table, side by side. Read-only. Proves the numbers on the dashboard are
            the numbers in the source.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-muted-foreground">
              From
              <Input
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
                className="mt-1 w-40"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              To
              <Input
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                className="mt-1 w-40"
              />
            </label>
            <Button
              variant="outline"
              disabled={parity.isPending}
              onClick={() => parity.mutate({ from, to })}
            >
              {parity.isPending ? "Checking..." : "Run parity check"}
            </Button>
          </div>
          {parity.isError && (
            <p className="text-sm text-destructive">
              {parity.error instanceof ApiError
                ? parity.error.message
                : "Parity check failed. Please try again."}
            </p>
          )}
          {report && !report.configured && (
            <p className="text-sm text-muted-foreground">{report.message}</p>
          )}
          {report && report.configured && report.message && (
            <p className="text-sm text-destructive">{report.message}</p>
          )}
          {report && report.configured && !report.message && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge variant={report.in_sync ? "default" : "destructive"}>
                  {report.in_sync ? "In sync" : `${report.mismatched.length} mismatched`}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {report.date_from} to {report.date_to}, tolerance{" "}
                  {(report.tolerance * 100).toFixed(1)}%
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="py-1 pr-3">Column</th>
                      <th className="py-1 pr-3 text-right">BigQuery</th>
                      <th className="py-1 pr-3 text-right">Postgres</th>
                      <th className="py-1 pr-3 text-right">Delta</th>
                      <th className="py-1">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.rows.map((row) => (
                      <tr key={row.column} className="border-t">
                        <td className="py-1 pr-3 font-mono text-xs">{row.column}</td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {formatNumber(row.bigquery)}
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {formatNumber(row.postgres)}
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {formatNumber(row.delta)}
                          {row.delta_pct !== null && (
                            <span className="ml-1 text-xs text-muted-foreground">
                              ({(row.delta_pct * 100).toFixed(2)}%)
                            </span>
                          )}
                        </td>
                        <td className="py-1">
                          {row.within_tolerance ? (
                            <span className="text-xs text-muted-foreground">ok</span>
                          ) : (
                            <Badge variant="destructive">mismatch</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

'''

EDITS: list[tuple[str, str, str, str]] = [
    # ── backend: schema, route, imports ─────────────────────────────────────────────
    (
        "backend/app/schemas/integration.py",
        "the report schema",
        "class SchemaSyncColumn(BaseModel):",
        SCHEMA_SRC + "class SchemaSyncColumn(BaseModel):",
    ),
    (
        "backend/app/api/v1/admin.py",
        "the schema import",
        "    IntegrationStatus,\n    SchemaDiff,\n",
        "    IntegrationStatus,\n    ParityReport,\n    SchemaDiff,\n",
    ),
    (
        "backend/app/api/v1/admin.py",
        "the service import",
        "    integration_service,\n",
        "    integration_service,\n    parity_service,\n",
    ),
    (
        "backend/app/api/v1/admin.py",
        "the route, beside the schema diff",
        '@router.get(\n    "/integration/schema-diff",\n    response_model=SchemaDiff,\n'
        "    dependencies=[Depends(enforce_diagnostics_rate_limit)],\n",
        ROUTE_SRC
        + '@router.get(\n    "/integration/schema-diff",\n    response_model=SchemaDiff,\n'
        "    dependencies=[Depends(enforce_diagnostics_rate_limit)],\n",
    ),
    # ── frontend: types, hook, panel ────────────────────────────────────────────────
    (
        "frontend/lib/api-hooks.ts",
        "the types",
        "export interface SchemaDiff {",
        TS_TYPES + "export interface SchemaDiff {",
    ),
    (
        "frontend/lib/api-hooks.ts",
        "the hook",
        "export function useSchemaDiff() {\n  return useMutation({\n"
        '    mutationFn: () => apiFetch<SchemaDiff>("/api/v1/admin/integration/schema-diff"),\n'
        "  });\n}\n",
        "export function useSchemaDiff() {\n  return useMutation({\n"
        '    mutationFn: () => apiFetch<SchemaDiff>("/api/v1/admin/integration/schema-diff"),\n'
        "  });\n}\n" + TS_HOOK,
    ),
    (
        "frontend/components/admin/integration-panel.tsx",
        "import the hook",
        '  useTestBigQuery,\n  useUpdateSetting,\n} from "@/lib/api-hooks";',
        '  useParityReport,\n  useTestBigQuery,\n  useUpdateSetting,\n} from "@/lib/api-hooks";',
    ),
    (
        "frontend/components/admin/integration-panel.tsx",
        "the section component",
        "function SchemaDiffSection() {",
        PANEL_SECTION + "function SchemaDiffSection() {",
    ),
    (
        "frontend/components/admin/integration-panel.tsx",
        "rendered under the schema diff",
        "      {/* B2) Schema diff (read-only, informational) */}\n      <SchemaDiffSection />",
        "      {/* B2) Schema diff (read-only, informational) */}\n      <SchemaDiffSection />\n\n"
        "      {/* B3) Parity: BigQuery vs Postgres totals (read-only, diagnostic) */}\n"
        "      <ParitySection />",
    ),
]


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 10)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1
    if "parity_service" in (ROOT / "backend/app/api/v1/admin.py").read_text():
        print("Already applied - left alone.")
        SERVICE.write_text(SERVICE_SRC)
        TEST.write_text(TEST_SRC)
        print(f"  - {SERVICE}: refreshed\n  - {TEST}: refreshed")
        return 0

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for rel, label, old, new in EDITS:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"  [{label}] {rel}: file missing")
            continue
        text = planned.get(path, path.read_text())
        if text.count(old) != 1:
            problems.append(
                f"  [{label}] {rel}: expected exactly 1 match, found {text.count(old)}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, new, 1)
    if problems:
        print("NOTHING WAS WRITTEN - a route without its schema, or a panel without its hook,")
        print("is a build failure, not a feature. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for path, text in planned.items():
        path.write_text(text)
    SERVICE.write_text(SERVICE_SRC)
    TEST.write_text(TEST_SRC)
    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for path in (*planned, SERVICE, TEST):
        print(f"  - {path}")
    print(
        "\nStated plainly: the BigQuery call itself is not exercised by the suite - the"
        "\ncomparison, the window validation, the view parsing and the not-configured path are."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

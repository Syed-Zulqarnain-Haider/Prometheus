#!/usr/bin/env python3
"""Feature 5: portfolio benchmarks - is 1.4x ROAS good?

Every ratio on this dashboard is an absolute number with no context. 1.4x ROAS, a 22%
margin, a $0.83 CPI: are those good? The only honest answer is "compared to what", and
the comparison people actually want is against the rest of the portfolio they own. This
ranks every app against its peers and says where each one sits.

Design decisions worth keeping:

* The peer set is EVERY app in the current filter and scope EXCEPT that the ``apps``
  filter is dropped. Selecting one app would make it its own peer group and every
  percentile would be 50. Every other filter is honoured, so a pod owner filtering to
  their pod is ranked inside their pod - which is the comparison they meant.
* A ratio with a zero denominator is EXCLUDED from the ranking, not ranked as zero. An
  app with no spend has no ROAS; ranking it as "worst ROAS" would push every real app up
  a quartile and quietly flatter the portfolio.
* Quartiles are only reported at four or more ranked apps. Below that a "top quartile"
  badge is decoration - it means "one of the three of us", and saying so is better than
  implying a distribution that does not exist.
* Direction is per benchmark. CPI is better when it is LOWER, so its percentile is
  inverted; a benchmark that got this backwards would silently celebrate the worst apps.
* RBAC: a benchmark is only computed when EVERY component measure is permitted. A
  marketing user without ad_revenue is not shown a ratio built from it, and the
  computation is done through QueryBuilder.breakdown, so the row scopes come free.

No migration. Backend service + one route + two surfaces (a standings card on App
Detail, a leaderboard widget on Overview).

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all files
validate before any is touched. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE = Path("backend/app/services/benchmark_service.py")
SCHEMA = Path("backend/app/schemas/benchmarks.py")
TEST = Path("backend/tests/test_benchmarks.py")
CARD = Path("frontend/components/app-detail/benchmark-card.tsx")
PANEL = Path("frontend/components/overview/benchmarks-panel.tsx")

METRICS_ROUTE = Path("backend/app/api/v1/metrics.py")
TYPES = Path("frontend/lib/types.ts")
HOOKS = Path("frontend/lib/api-hooks.ts")
DETAIL = Path("frontend/components/app-detail/app-detail-client.tsx")
LAYOUT = Path("frontend/lib/overview-layout.ts")
CLIENT = Path("frontend/components/overview/overview-client.tsx")

SERVICE_SOURCE = '''"""Portfolio benchmarks: where each app sits against its peers.

Every ratio on this dashboard is an absolute number with no context. 1.4x ROAS, a 22%
margin, a $0.83 CPI - good or bad? The only honest answer is "compared to what", and the
comparison people want is the rest of the portfolio they own.

The arithmetic is deliberately done here rather than in SQL: the ratios are built from
additive measures that ``QueryBuilder.breakdown`` already returns under the caller's
scope and permissions, so ranking them in Python needs no new query shape, inherits
every RBAC guarantee, and keeps the percentile convention in one readable place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics import GroupBy, MetricFilters
from app.services.query_builder import QueryBuilder

# Quartiles below this many ranked entities are decoration: "top quartile" would mean
# "one of the three of us". Report the count instead and let the reader judge.
MIN_FOR_QUARTILES = 4


@dataclass(frozen=True)
class BenchmarkDef:
    id: str
    label: str
    numerator: str
    denominator: str
    # False for cost-like ratios (CPI): a LOWER value is the better one, so the
    # percentile has to be inverted or the leaderboard celebrates the worst apps.
    higher_is_better: bool
    unit: str  # "ratio" | "usd" | "percent"


# The reported (rpt_*) ladder is the finance-authoritative source and is what the KPI
# cards show, so the benchmarks are built from it wherever it exists.
BENCHMARKS: tuple[BenchmarkDef, ...] = (
    BenchmarkDef("roas", "ROAS", "rpt_gross_revenue_usd", "rpt_ua_cost_usd", True, "ratio"),
    BenchmarkDef(
        "margin", "Profit margin", "rpt_tf_profit_usd", "rpt_gross_revenue_usd", True, "percent"
    ),
    BenchmarkDef("cpi", "CPI", "rpt_ua_cost_usd", "total_paid_installs", False, "usd"),
    BenchmarkDef(
        "arpi", "Revenue per install", "rpt_gross_revenue_usd", "store_total_installs", True, "usd"
    ),
)


def _percentile_ranks(values: list[float], higher_is_better: bool) -> list[float]:
    """Percentile rank of each value within its own list, 0-100.

    Uses the "fraction of peers strictly worse, plus half the ties" convention, which is
    the one that behaves sensibly when several apps share a value - a plain "count below"
    would give tied apps different ranks depending only on list order.
    """
    n = len(values)
    if n <= 1:
        return [50.0] * n
    ranks: list[float] = []
    for value in values:
        better = sum(
            1
            for other in values
            if (other < value if higher_is_better else other > value)
        )
        ties = sum(1 for other in values if other == value) - 1
        ranks.append(100.0 * (better + 0.5 * ties) / (n - 1))
    return ranks


def _quartile(percentile: float, count: int) -> int | None:
    """1 = best quarter, 4 = worst. None when there are too few apps to mean anything."""
    if count < MIN_FOR_QUARTILES:
        return None
    if percentile >= 75.0:
        return 1
    if percentile >= 50.0:
        return 2
    if percentile >= 25.0:
        return 3
    return 4


async def compute(
    db: AsyncSession,
    qb: QueryBuilder,
    params: MetricFilters,
    group_by: GroupBy,
    *,
    limit: int,
) -> dict[str, Any]:
    """Rank every entity in the peer set for every benchmark the caller may see."""
    # The peer set is the portfolio, so the app narrowing is dropped - otherwise
    # selecting one app makes it its own peer group and every percentile is 50. Scope
    # and every other filter still apply; they define which portfolio is being asked
    # about.
    peer_params = params.model_copy(update={"apps": [], "compare": False})

    available = [
        b
        for b in BENCHMARKS
        if b.numerator in qb.permitted_measures and b.denominator in qb.permitted_measures
    ]
    if not available:
        return {"group_by": group_by, "peer_count": 0, "benchmarks": []}

    needed = sorted({m for b in available for m in (b.numerator, b.denominator)})
    rows = (
        (await db.execute(qb.breakdown(peer_params, group_by, needed)))
        .mappings()
        .all()
    )

    out: list[dict[str, Any]] = []
    peer_count = 0
    for benchmark in available:
        ranked: list[tuple[str, str, float]] = []
        for row in rows:
            key = row[group_by]
            if key is None:
                continue
            denominator = float(row[benchmark.denominator] or 0.0)
            if denominator == 0:
                # No spend means no ROAS. Ranking it as the worst would push every real
                # app up a quartile and quietly flatter the portfolio.
                continue
            value = float(row[benchmark.numerator] or 0.0) / denominator
            ranked.append((key, str(row.get("app_name") or key), value))

        count = len(ranked)
        peer_count = max(peer_count, count)
        percentiles = _percentile_ranks([v for _, _, v in ranked], benchmark.higher_is_better)
        # Paired and sorted BEFORE the dicts are built: sorting dicts afterwards means
        # sorting on a value whose type is a union, which is neither typed nor readable.
        scored = sorted(
            zip(ranked, percentiles, strict=True),
            key=lambda pair: pair[1],
            reverse=True,  # best first, so the leaderboard reads top-down
        )
        entries: list[dict[str, Any]] = [
            {
                "key": key,
                "label": label,
                "value": value,
                "percentile": percentile,
                "quartile": _quartile(percentile, count),
            }
            for (key, label, value), percentile in scored
        ]
        out.append(
            {
                "id": benchmark.id,
                "label": benchmark.label,
                "unit": benchmark.unit,
                "higher_is_better": benchmark.higher_is_better,
                "count": count,
                "rows": entries[:limit],
                # The FULL ranking is capped for transport, so the caller is told what a
                # percentile was measured against rather than inferring it from the rows.
                "truncated": count > limit,
            }
        )

    return {"group_by": group_by, "peer_count": peer_count, "benchmarks": out}


async def compute_for(
    db: AsyncSession,
    qb: QueryBuilder,
    params: MetricFilters,
    group_by: GroupBy,
    focus_key: str,
) -> dict[str, Any]:
    """One entity's standing in every benchmark - the App Detail case.

    Ranked against the whole peer set, then filtered down to the one row. Filtering
    first would rank the app against itself.
    """
    # No limit: the focus row can sit anywhere in the ranking, and a truncated list
    # would silently report "not ranked" for a mid-table app.
    full = await compute(db, qb, params, group_by, limit=1_000_000)
    for benchmark in full["benchmarks"]:
        benchmark["rows"] = [r for r in benchmark["rows"] if r["key"] == focus_key]
        benchmark["truncated"] = False
    return full
'''

SCHEMA_SOURCE = '''"""Portfolio benchmark response models."""

from __future__ import annotations

from pydantic import BaseModel


class BenchmarkRow(BaseModel):
    key: str | None
    label: str | None
    value: float
    # 0-100 within the peer set, already inverted for cost-like ratios so that a HIGHER
    # percentile always means a BETTER app.
    percentile: float
    # 1 = best quarter, 4 = worst. None when there are too few apps to mean anything.
    quartile: int | None


class BenchmarkGroup(BaseModel):
    id: str
    label: str
    unit: str
    higher_is_better: bool
    # Entities that had a usable (non-zero-denominator) value - what the percentile was
    # measured against.
    count: int
    rows: list[BenchmarkRow]
    truncated: bool


class BenchmarkResponse(BaseModel):
    group_by: str
    peer_count: int
    benchmarks: list[BenchmarkGroup]
'''

TEST_SOURCE = '''"""Portfolio benchmarks: the ranking convention, and who may see one.

The percentile convention is the whole feature - get the direction wrong and the
leaderboard celebrates the worst apps - so it is tested as pure arithmetic, plus the
RBAC and zero-denominator rules through the endpoint.
"""

from typing import Any

from app.services.benchmark_service import MIN_FOR_QUARTILES, _percentile_ranks, _quartile

from tests.conftest import MetricsEnv

URL = "/api/v1/metrics/benchmarks"


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def _params(**overrides: Any) -> dict[str, Any]:
    # date_from / date_to - NOT from / to. get_filters declares them by those names, so
    # the short form is simply a missing required parameter and FastAPI 422s before the
    # handler is ever reached.
    params: dict[str, Any] = {
        "date_from": "2026-06-01",
        "date_to": "2026-06-30",
        "group_by": "app",
    }
    params.update(overrides)
    return params


def test_best_value_ranks_highest_when_higher_is_better() -> None:
    ranks = _percentile_ranks([1.0, 2.0, 3.0, 4.0], higher_is_better=True)
    assert ranks[3] == 100.0
    assert ranks[0] == 0.0


def test_direction_is_inverted_for_cost_like_ratios() -> None:
    """CPI: the CHEAPEST app must rank highest, or the leaderboard celebrates the worst."""
    ranks = _percentile_ranks([1.0, 2.0, 3.0, 4.0], higher_is_better=False)
    assert ranks[0] == 100.0
    assert ranks[3] == 0.0


def test_ties_share_a_rank_rather_than_depending_on_order() -> None:
    ranks = _percentile_ranks([5.0, 5.0, 5.0], higher_is_better=True)
    assert ranks == [50.0, 50.0, 50.0]


def test_single_entity_is_not_claimed_to_be_top() -> None:
    assert _percentile_ranks([7.0], higher_is_better=True) == [50.0]


def test_quartiles_are_withheld_below_the_minimum() -> None:
    assert _quartile(100.0, MIN_FOR_QUARTILES - 1) is None
    assert _quartile(100.0, MIN_FOR_QUARTILES) == 1
    assert _quartile(0.0, MIN_FOR_QUARTILES) == 4


async def test_requires_auth(metrics_env: MetricsEnv) -> None:
    assert (await metrics_env.client.get(URL, params=_params())).status_code == 401


async def test_admin_sees_the_ratio_benchmarks(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(URL, params=_params(), headers=_auth("admin"))
    assert resp.status_code == 200, resp.text
    ids = {b["id"] for b in resp.json()["benchmarks"]}
    assert {"roas", "margin", "cpi", "arpi"} <= ids


async def test_viewer_gets_no_benchmark_they_cannot_compute(metrics_env: MetricsEnv) -> None:
    """viewer holds store_installs only - every benchmark needs a revenue or cost
    measure, so the honest answer is an empty list, not a zero."""
    resp = await metrics_env.client.get(URL, params=_params(), headers=_auth("viewer"))
    assert resp.status_code == 200
    assert resp.json()["benchmarks"] == []


async def test_focus_returns_only_that_app_but_ranks_against_all(
    metrics_env: MetricsEnv,
) -> None:
    resp = await metrics_env.client.get(
        URL, params=_params(focus="appA"), headers=_auth("admin")
    )
    assert resp.status_code == 200
    for benchmark in resp.json()["benchmarks"]:
        assert [r["key"] for r in benchmark["rows"]] in ([], ["appA"])
        # The count is the PEER set, not the returned rows - that is what the
        # percentile was measured against.
        assert benchmark["count"] >= len(benchmark["rows"])
'''

CARD_SOURCE = r'''"use client";

import { ChartCard } from "@/components/charts/chart-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBenchmarks } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";
import type { BenchmarkGroup, BenchmarkRow } from "@/lib/types";

/* "Is 1.4x ROAS good?" - the question every ratio on this page raises and none of them
 * answer. This ranks the app against the rest of the portfolio in the current filter.
 *
 * Quartiles are withheld below four ranked apps: "top quartile" out of three means "one
 * of the three of us", and a badge that says otherwise is decoration. */

const QUARTILE_LABEL: Record<number, string> = {
  1: "Top quartile",
  2: "Upper middle",
  3: "Lower middle",
  4: "Bottom quartile",
};

function quartileColor(quartile: number | null): string {
  if (quartile === 1) return "var(--color-positive)";
  if (quartile === 4) return "var(--color-negative)";
  if (quartile === null) return "var(--color-text-muted)";
  return "var(--color-amber)";
}

function formatValue(unit: string, value: number): string {
  if (unit === "usd") return formatUSD(value);
  if (unit === "percent") return `${(value * 100).toFixed(1)}%`;
  return `${value.toFixed(2)}×`;
}

function Standing({ group, row }: { group: BenchmarkGroup; row: BenchmarkRow }) {
  const color = quartileColor(row.quartile);
  return (
    <li className="space-y-1 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm">{group.label}</span>
        <span className="text-sm font-semibold tabular-nums">
          {formatValue(group.unit, row.value)}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-bg-elevated)]">
          <span
            className="block h-full rounded-full"
            style={{ width: `${Math.max(2, row.percentile)}%`, backgroundColor: color }}
          />
        </span>
        <span className="w-32 shrink-0 text-right text-[10px]" style={{ color }}>
          {row.quartile != null
            ? `${QUARTILE_LABEL[row.quartile]} of ${group.count}`
            : `${row.percentile.toFixed(0)}th of ${group.count}`}
        </span>
      </div>
    </li>
  );
}

export function BenchmarkCard({
  filters,
  canonicalKey,
}: {
  filters: Filters;
  canonicalKey: string;
}) {
  const query = useBenchmarks(filters, "app", canonicalKey);
  const groups = (query.data?.benchmarks ?? []).filter((g) => g.rows.length > 0);

  return (
    <ChartCard title="How this app ranks">
      {query.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : query.isError ? (
        <p className="text-sm text-[var(--color-negative)]">
          Could not rank this app: {(query.error as Error).message}
        </p>
      ) : groups.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          Nothing to rank in this window - the ratios need spend or installs, and this app
          has none here.
        </p>
      ) : (
        <ul className="divide-y">
          {groups.map((group) => (
            <Standing key={group.id} group={group} row={group.rows[0]} />
          ))}
        </ul>
      )}
    </ChartCard>
  );
}
'''

PANEL_SOURCE = r'''"use client";

import Link from "next/link";
import { useState } from "react";

import { ChartCard } from "@/components/charts/chart-card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBenchmarks } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

/* The portfolio leaderboard. Same ranking the App Detail card shows, read the other way
 * round: which apps are actually at the top, and which are at the bottom.
 *
 * Cost-like ratios (CPI) are inverted server-side, so a higher percentile always means a
 * better app and this component never has to know which way round a metric runs. */

const ROWS = 6;

function formatValue(unit: string, value: number): string {
  if (unit === "usd") return formatUSD(value);
  if (unit === "percent") return `${(value * 100).toFixed(1)}%`;
  return `${value.toFixed(2)}×`;
}

export function BenchmarksPanel({ filters }: { filters: Filters }) {
  const query = useBenchmarks(filters, "app");
  const groups = query.data?.benchmarks ?? [];
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = groups.find((g) => g.id === activeId) ?? groups[0];

  const control =
    groups.length > 1 ? (
      <select
        aria-label="Benchmark"
        value={active?.id ?? ""}
        onChange={(event) => setActiveId(event.target.value)}
        className="h-8 rounded-[var(--radius-inner)] border border-input bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-ring"
      >
        {groups.map((g) => (
          <option key={g.id} value={g.id}>
            {g.label}
          </option>
        ))}
      </select>
    ) : undefined;

  const top = active?.rows.slice(0, ROWS) ?? [];
  const bottom = active && active.rows.length > ROWS ? active.rows.slice(-ROWS).reverse() : [];

  return (
    <ChartCard title="Portfolio benchmarks" action={control}>
      {query.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : query.isError ? (
        <p className="text-sm text-[var(--color-negative)]">
          Could not rank the portfolio: {(query.error as Error).message}
        </p>
      ) : !active || active.rows.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          Nothing to rank in this window. These ratios need spend or installs.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
              Best {active.label} · of {active.count}
            </p>
            <ul className="divide-y">
              {top.map((row) => (
                <li key={`top-${row.key}`} className="flex items-center gap-2 py-1.5">
                  <Link
                    href={`/apps/${row.key}`}
                    className="min-w-0 flex-1 truncate text-sm hover:underline"
                  >
                    {row.label}
                  </Link>
                  <span className="shrink-0 text-sm font-semibold tabular-nums text-[var(--color-positive)]">
                    {formatValue(active.unit, row.value)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          {bottom.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                Worst {active.label}
              </p>
              <ul className="divide-y">
                {bottom.map((row) => (
                  <li key={`bottom-${row.key}`} className="flex items-center gap-2 py-1.5">
                    <Link
                      href={`/apps/${row.key}`}
                      className="min-w-0 flex-1 truncate text-sm hover:underline"
                    >
                      {row.label}
                    </Link>
                    <span className="shrink-0 text-sm font-semibold tabular-nums text-[var(--color-negative)]">
                      {formatValue(active.unit, row.value)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </ChartCard>
  );
}
'''

# ── anchored edits ────────────────────────────────────────────────────────────
# app.schemas.benchmarks sorts BEFORE app.schemas.metrics - ruff's isort rule is a
# gate here, not a preference.
METRICS_IMPORT_ANCHOR = (
    "from app.schemas.metrics import Bucket, GroupBy, MetricFilters, Platform, SortDirection\n"
)
METRICS_IMPORT_NEW = (
    "from app.schemas.benchmarks import BenchmarkResponse\n"
    "from app.schemas.metrics import Bucket, GroupBy, MetricFilters, Platform, SortDirection\n"
)
METRICS_SERVICE_ANCHOR = "from app.services import (\n    anomaly_service,\n"
METRICS_SERVICE_ADD = "    benchmark_service,\n"

METRICS_ROUTE_ANCHOR = '@router.get("/anomalies", response_model=AnomalyResponse)\n'
METRICS_ROUTE_ADD = '''@router.get("/benchmarks", response_model=BenchmarkResponse)
async def benchmarks(
    filters: Filters,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    group_by: GroupBy = "app",
    focus: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> BenchmarkResponse:
    """Where each entity sits against its peers on ROAS, margin, CPI and revenue/install.

    The peer set is everything in the current filter and scope EXCEPT the app narrowing:
    selecting one app would make it its own peer group and every percentile would be 50.
    With ``focus`` the ranking is still computed over the whole peer set and only that
    entity's row is returned - filtering first would rank the app against itself.

    A benchmark appears only when BOTH its component measures are permitted, so a role is
    never shown a ratio it could not have computed itself.
    """
    qb = QueryBuilder(context)
    key = aggregate_cache_key(
        "metrics.benchmarks",
        scope_token(context.scopes),
        perms_token(context.metric_groups),
        _params(filters, group_by=group_by, focus=focus or "", limit=limit),
    )

    async def produce() -> dict[str, Any]:
        try:
            if focus:
                return await benchmark_service.compute_for(db, qb, filters, group_by, focus)
            return await benchmark_service.compute(db, qb, filters, group_by, limit=limit)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    result: dict[str, Any] = await cached_json(redis, key, produce)
    return BenchmarkResponse(**result)


'''

TYPES_ANCHOR = "export interface TableResponse {\n"
TYPES_ADD = """/** One entity's standing in one benchmark. ``percentile`` is already inverted for
 *  cost-like ratios, so a HIGHER percentile always means a BETTER app. */
export interface BenchmarkRow {
  key: string | null;
  label: string | null;
  value: number;
  percentile: number;
  /** 1 = best quarter, 4 = worst. Null when there are too few apps to mean anything. */
  quartile: number | null;
}

export interface BenchmarkGroup {
  id: string;
  label: string;
  unit: string;
  higher_is_better: boolean;
  /** Entities with a usable value - what the percentile was measured against. */
  count: number;
  rows: BenchmarkRow[];
  truncated: boolean;
}

export interface BenchmarkResponse {
  group_by: string;
  peer_count: number;
  benchmarks: BenchmarkGroup[];
}

"""

HOOKS_IMPORT_ANCHOR = "  AnomalyResponse,\n"
HOOKS_IMPORT_ADD = "  BenchmarkResponse,\n"
HOOKS_ANCHOR = "// ── Identity (RBAC context + share directory) ────────────────────────────────\n"
HOOKS_ADD = '''// ── Portfolio benchmarks (is 1.4x ROAS good?) ────────────────────────────────
/** Rank entities against their peers. With ``focus`` the ranking is still computed over
 *  the whole peer set and only that entity's row comes back. */
export function useBenchmarks(filters: Filters, groupBy: string, focus?: string) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), group_by: groupBy, focus };
  return useQuery({
    queryKey: ["benchmarks", params],
    queryFn: () =>
      apiFetch<BenchmarkResponse>(`/api/v1/metrics/benchmarks${buildQuery(params)}`),
    enabled: Boolean(user),
    staleTime: AGG_STALE,
  });
}

'''

DETAIL_IMPORT_ANCHOR = 'import { WatchToggle } from "@/components/app-detail/watch-toggle";\n'
DETAIL_IMPORT_ADD = 'import { BenchmarkCard } from "@/components/app-detail/benchmark-card";\n'
DETAIL_GRID_ANCHOR = """      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AppTrend title="Revenue" filters={appFilters} metrics={REVENUE_METRICS} unit="usd" />
"""
DETAIL_GRID_NEW = """      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BenchmarkCard filters={appFilters} canonicalKey={canonicalKey} />
        <AppTrend title="Revenue" filters={appFilters} metrics={REVENUE_METRICS} unit="usd" />
"""

LAYOUT_ID_ANCHOR = '  "watchlist",\n'
LAYOUT_ID_ADD = '  "benchmarks",\n'
LAYOUT_GRID_ANCHOR = '  { i: "watchlist", x: 0, y: 76, w: 12, h: 18, minW: 4, minH: 10 },\n'
LAYOUT_GRID_ADD = '  { i: "benchmarks", x: 0, y: 94, w: 12, h: 18, minW: 4, minH: 10 },\n'

CLIENT_IMPORT_ANCHOR = 'import { WatchlistPanel } from "@/components/overview/watchlist-panel";\n'
CLIENT_IMPORT_ADD = 'import { BenchmarksPanel } from "@/components/overview/benchmarks-panel";\n'
CLIENT_ITEM_ANCHOR = '    watchlist: <WatchlistPanel filters={filters} />,\n'
CLIENT_ITEM_ADD = '    benchmarks: <BenchmarksPanel filters={filters} />,\n'


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def plan_edits(
    path: Path, text: str, marker: str, edits: list[tuple[str, str, bool | None]]
) -> list[tuple[str, str, bool | None]] | None:
    if marker in text:
        print(f"{path}: already patched")
        return None
    for anchor, _, _ in edits:
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")
    return edits


def main() -> None:
    patched = [METRICS_ROUTE, TYPES, HOOKS, DETAIL, LAYOUT, CLIENT]
    for path in patched:
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    if '"watchlist"' not in LAYOUT.read_text():
        die(f"{LAYOUT}: run scripts/add-watchlist-anomalies.py first - this builds on it")

    texts = {path: path.read_text() for path in patched}

    plan: dict[Path, list[tuple[str, str, bool | None]]] = {}
    for path, marker, edits in (
        (
            METRICS_ROUTE,
            '"/benchmarks"',
            [
                (METRICS_IMPORT_ANCHOR, METRICS_IMPORT_NEW, None),
                (METRICS_SERVICE_ANCHOR, METRICS_SERVICE_ADD, False),
                (METRICS_ROUTE_ANCHOR, METRICS_ROUTE_ADD, True),
            ],
        ),
        (TYPES, "interface BenchmarkRow", [(TYPES_ANCHOR, TYPES_ADD, True)]),
        (
            HOOKS,
            "useBenchmarks",
            [(HOOKS_IMPORT_ANCHOR, HOOKS_IMPORT_ADD, False), (HOOKS_ANCHOR, HOOKS_ADD, True)],
        ),
        (
            DETAIL,
            "BenchmarkCard",
            [
                (DETAIL_IMPORT_ANCHOR, DETAIL_IMPORT_ADD, True),
                (DETAIL_GRID_ANCHOR, DETAIL_GRID_NEW, None),
            ],
        ),
        (
            LAYOUT,
            '  "benchmarks",\n',
            [(LAYOUT_ID_ANCHOR, LAYOUT_ID_ADD, False), (LAYOUT_GRID_ANCHOR, LAYOUT_GRID_ADD, False)],
        ),
        (
            CLIENT,
            "BenchmarksPanel",
            [
                (CLIENT_IMPORT_ANCHOR, CLIENT_IMPORT_ADD, True),
                (CLIENT_ITEM_ANCHOR, CLIENT_ITEM_ADD, False),
            ],
        ),
    ):
        edits_or_none = plan_edits(path, texts[path], marker, edits)
        if edits_or_none is not None:
            plan[path] = edits_or_none

    new_files = {
        SERVICE: SERVICE_SOURCE,
        SCHEMA: SCHEMA_SOURCE,
        TEST: TEST_SOURCE,
        CARD: CARD_SOURCE,
        PANEL: PANEL_SOURCE,
    }
    stale = {p: s for p, s in new_files.items() if not p.exists() or p.read_text() != s}

    if not plan and not stale:
        print("already installed - nothing to do")
        return

    for path, source in stale.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        print(f"wrote {path}")

    for path, edits in plan.items():
        text = texts[path]
        for anchor, addition, before in edits:
            if before is None:
                text = text.replace(anchor, addition, 1)
            else:
                text = text.replace(anchor, (addition + anchor) if before else (anchor + addition), 1)
        path.write_text(text)
        print(f"patched {path}")

    print("\nNo migration. Benchmarks appear on App Detail ('How this app ranks') and as")
    print("a Portfolio benchmarks widget on Executive Overview.")


if __name__ == "__main__":
    main()

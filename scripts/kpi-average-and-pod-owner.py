#!/usr/bin/env python3
"""Daily average on the KPI cards, and a pod table keyed on the OWNER.

A. KPI cards
   - an "Avg / day" figure under each dollar card, revenue-to-date divided by the
     days in the selected range;
   - a 7-day moving average drawn over each sparkline, with the daily series
     dropped back to a hairline so the smoothed line is the one you read.
   Profit % gets a sparkline it never had (daily margin) so it can carry an
   average line too, but deliberately gets NO "Avg / day" number - see below.

B. Pod table -> Pod Owner
   The Overview table keys on the person, not the pod, and each owner links to
   their own page: their totals, their trend, and the pods they own.

Nothing is written unless every anchor resolves exactly once. Re-running is a no-op.
Revert: git checkout -- frontend/ && rm -rf "frontend/app/(app)/pod-owner"
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"

CARD = FE / "components" / "overview" / "kpi-card.tsx"
ROW = FE / "components" / "overview" / "kpi-row.tsx"
POD_TABLE = FE / "components" / "overview" / "pod-table.tsx"
OWNER_TABLE = FE / "components" / "pod-owners" / "pod-owner-table.tsx"
DETAIL = FE / "app" / "(app)" / "pod-owner" / "[owner]" / "page.tsx"

problems: list[str] = []
notes: list[str] = []
writes: dict[Path, str] = {}


def fail(message: str) -> None:
    problems.append(message)


def note(message: str) -> None:
    notes.append(message)


def swap(path: Path, source: str, old: str, new: str, what: str) -> str | None:
    count = source.count(old)
    if count != 1:
        fail(f"{path.relative_to(ROOT)}: {what} matched {count} times, expected 1")
        head = old.strip().splitlines()[0][:70]
        for number, line in enumerate(source.splitlines(), 1):
            if head and head in line:
                print(f"    on disk {path.relative_to(ROOT)}:{number}: {line}")
        return None
    note(f"  {path.relative_to(ROOT)}: {what}")
    return source.replace(old, new, 1)


def swap_comment(path: Path, source: str, old: str, new: str, what: str) -> str:
    """A prose-only swap. Reported when it misses, but never blocks the batch -
    a stale comment is worth fixing and not worth failing a deploy over."""
    if source.count(old) == 1:
        note(f"  {path.relative_to(ROOT)}: {what}")
        return source.replace(old, new, 1)
    note(f"  {path.relative_to(ROOT)}: SKIPPED (comment not matched) - {what}")
    return source


def add_import(source: str, statement: str) -> str:
    if statement in source:
        return source
    ends = [m.end() for m in re.finditer(r'^(?:import [^\n]*?;|\} from "[^"]+";)$', source, re.M)]
    if not ends:
        fail("no import block to extend")
        return source
    cut = max(ends)
    return source[:cut] + "\n" + statement + source[cut:]


# ═══════════════════════════════════════════════════ A. the KPI card ═════════
OLD_SIG = '''function sparklineOption(
  values: number[],
  color: string,
  dates?: string[],
  format?: (value: number) => string,
): EChartsOption {
  return {'''

NEW_SIG = '''/** Days averaged by the smoothed line. A week absorbs the weekday/weekend shape that
 *  makes every daily revenue series look jagged, without flattening a real move. */
const MA_WINDOW = 7;

function sparklineOption(
  values: (number | null)[],
  color: string,
  dates?: string[],
  format?: (value: number) => string,
): EChartsOption {
  // Only once a full window exists. Below that movingAverage is null at every point and
  // the second line would be an empty promise drawn across the card.
  const average = values.length > MA_WINDOW ? movingAverage(values, MA_WINDOW) : null;
  return {'''

OLD_POINT = '''        const point = (Array.isArray(params) ? params[0] : params) as {
          axisValue?: string | number;
          data?: number | null;
        };'''

NEW_POINT = '''        const points = (Array.isArray(params) ? params : [params]) as {
          axisValue?: string | number;
          data?: number | null;
          seriesName?: string;
        }[];
        const point = points[0] ?? {};'''

OLD_RETURN = '''        return `${label} · ${(format ?? formatUSD)(Number(point.data ?? 0))}`;'''

NEW_RETURN = '''        const show = format ?? formatUSD;
        // Skip series with no value at this point rather than printing a zero: the
        // moving average is genuinely absent for the first six days, not zero there.
        const rows = points
          .filter((entry) => entry.data != null)
          .map((entry) => `${entry.seriesName ?? "Daily"} ${show(Number(entry.data))}`);
        return `${label}<br/>${rows.join("<br/>")}`;'''

OLD_DAILY = '''        type: "line",
        data: values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.75, color },'''

NEW_DAILY = '''        type: "line",
        name: "Daily",
        data: values,
        smooth: true,
        showSymbol: false,
        // Faint once an average rides on top: two lines of equal weight inside a 48px
        // sparkline read as noise, and the smoothed one is the one to follow.
        lineStyle: { width: average ? 1 : 1.75, color, opacity: average ? 0.4 : 1 },'''

OLD_SERIES_END = '''            ],
          },
        },
      },
    ],
  };
}'''

NEW_SERIES_END = '''            ],
          },
        },
      },
      {
        // Always declared, empty when there is no full window yet - a conditional
        // spread here defeats the series type inference for no benefit.
        type: "line",
        name: `${MA_WINDOW}-day avg`,
        data: average ?? [],
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color },
        z: 3,
      },
    ],
  };
}'''

OLD_PROPS = '''  spark?: number[];
  /** Daily dates aligned with ``spark`` - hovering shows that day's value. */
  sparkDates?: string[];'''

NEW_PROPS = '''  spark?: (number | null)[];
  /** Daily dates aligned with ``spark`` - hovering shows that day's value. */
  sparkDates?: string[];
  /** Already-formatted daily average for the selected range, e.g. "$7.2K". */
  average?: string;'''

OLD_DESTRUCTURE = '''  spark,
  sparkDates,
  sparkFormat,
  description,
  loading,
}: {'''

NEW_DESTRUCTURE = '''  spark,
  sparkDates,
  sparkFormat,
  average,
  description,
  loading,
}: {'''

OLD_DELTA_BLOCK = '''        </div>
      </div>

      {/* Always reserve the sparkline area so every card is the SAME height, even the
          ones without a sparkline (e.g. Profit %). */}'''

NEW_DELTA_BLOCK = '''        </div>

        {/* Reserved whether or not there is an average, so a card without one keeps the
            same height as the rest of the row. */}
        <div className="min-h-[16px]">
          {!loading && average && (
            <span className="text-[11px] tabular-nums text-muted-foreground">
              <span className="uppercase tracking-[0.1em]">Avg / day</span>{" "}
              <span className="font-semibold text-card-foreground">{average}</span>
            </span>
          )}
        </div>
      </div>

      {/* Always reserve the sparkline area so every card is the SAME height, even the
          ones without a sparkline (e.g. Profit %). */}'''


def patch_card() -> None:
    source = CARD.read_text(encoding="utf-8") if CARD.exists() else None
    if source is None:
        fail(f"missing: {CARD.relative_to(ROOT)}")
        return
    if "MA_WINDOW" in source:
        note("kpi-card.tsx already draws a moving average - left as is.")
        return
    out: str | None = source
    for old, new, what in (
        (OLD_SIG, NEW_SIG, "moving average computed for the sparkline"),
        (OLD_POINT, NEW_POINT, "tooltip reads every series, not just the first"),
        (OLD_RETURN, NEW_RETURN, "tooltip lists daily and average"),
        (OLD_DAILY, NEW_DAILY, "daily series drops to a hairline behind the average"),
        (OLD_SERIES_END, NEW_SERIES_END, "average series added"),
        (OLD_PROPS, NEW_PROPS, "average prop"),
        (OLD_DESTRUCTURE, NEW_DESTRUCTURE, "average destructured"),
        (OLD_DELTA_BLOCK, NEW_DELTA_BLOCK, "Avg / day row"),
    ):
        if out is None:
            return
        out = swap(CARD, out, old, new, what)
    if out is None:
        return
    writes[CARD] = add_import(out, 'import { movingAverage } from "@/lib/moving-average";')


# ═══════════════════════════════════════════════════ A. the KPI row ══════════
OLD_MARGIN_PREV = '''  const profitPctPrev = margin(previous?.rpt_tf_profit_usd, previous?.rpt_gross_revenue_usd);'''

NEW_MARGIN_PREV = '''  const profitPctPrev = margin(previous?.rpt_tf_profit_usd, previous?.rpt_gross_revenue_usd);

  // Profit % had no sparkline at all, so there was nothing for an average line to ride
  // on. Its daily series is the daily margin, computed with the SAME guard as the
  // headline figure: a day with no revenue is null, not 0% - a zero would be drawn as a
  // real collapse to nothing.
  const marginSpark: (number | null)[] =
    revenueSpark.length === profitSpark.length
      ? revenueSpark.map((revenue, index) =>
          revenue ? profitSpark[index] / revenue : null,
        )
      : [];

  // Days in the SELECTED RANGE, not the number of buckets that came back: a day with no
  // rows is still a day the average has to account for, and dividing by the rows present
  // would quietly inflate every figure whenever the feed is short.
  const days = (() => {
    const span =
      differenceInCalendarDays(parseISO(filters.dateTo), parseISO(filters.dateFrom)) + 1;
    return Number.isFinite(span) && span > 0 ? span : 0;
  })();

  /** The daily average of a period total, already formatted. */
  const perDay = (total?: number | null): string | undefined =>
    total == null || days === 0 ? undefined : formatUSD(total / days, { compact: true });'''

OLD_KPIS = '''  const kpis = [
    { label: "Revenue", field: "rpt_gross_revenue_usd", value: formatUSD(current.rpt_gross_revenue_usd), current: current.rpt_gross_revenue_usd, previous: previous?.rpt_gross_revenue_usd, spark: revenueSpark, description: "Reported gross revenue for the selected period." },
    { label: "Spend", field: "rpt_ua_cost_usd", value: formatUSD(current.rpt_ua_cost_usd), current: current.rpt_ua_cost_usd, previous: previous?.rpt_ua_cost_usd, spark: uaCostSpark, description: "Reported user-acquisition cost for the selected period." },
    { label: "Partners Share, Fees & Taxes", field: "rpt_shares_fees_taxes_usd", value: formatUSD(current.rpt_shares_fees_taxes_usd), current: current.rpt_shares_fees_taxes_usd, previous: previous?.rpt_shares_fees_taxes_usd, spark: sharesSpark, description: "Partners' share plus fees and taxes for the selected period." },
    { label: "TF Profit", field: "rpt_tf_profit_usd", value: formatUSD(current.rpt_tf_profit_usd), current: current.rpt_tf_profit_usd, previous: previous?.rpt_tf_profit_usd, spark: profitSpark, description: "Terafort reported gross profit for the selected period." },
    { label: "Profit %", field: "rpt_profit_margin", value: formatPercent(profitPct), current: profitPct, previous: profitPctPrev, spark: undefined, description: "Reported profit as a percentage of reported gross revenue." },
  ];'''

NEW_KPIS = '''  const kpis = [
    { label: "Revenue", field: "rpt_gross_revenue_usd", value: formatUSD(current.rpt_gross_revenue_usd), current: current.rpt_gross_revenue_usd, previous: previous?.rpt_gross_revenue_usd, spark: revenueSpark, sparkFormat: undefined, average: perDay(current.rpt_gross_revenue_usd), description: "Reported gross revenue for the selected period." },
    { label: "Spend", field: "rpt_ua_cost_usd", value: formatUSD(current.rpt_ua_cost_usd), current: current.rpt_ua_cost_usd, previous: previous?.rpt_ua_cost_usd, spark: uaCostSpark, sparkFormat: undefined, average: perDay(current.rpt_ua_cost_usd), description: "Reported user-acquisition cost for the selected period." },
    { label: "Partners Share, Fees & Taxes", field: "rpt_shares_fees_taxes_usd", value: formatUSD(current.rpt_shares_fees_taxes_usd), current: current.rpt_shares_fees_taxes_usd, previous: previous?.rpt_shares_fees_taxes_usd, spark: sharesSpark, sparkFormat: undefined, average: perDay(current.rpt_shares_fees_taxes_usd), description: "Partners' share plus fees and taxes for the selected period." },
    { label: "TF Profit", field: "rpt_tf_profit_usd", value: formatUSD(current.rpt_tf_profit_usd), current: current.rpt_tf_profit_usd, previous: previous?.rpt_tf_profit_usd, spark: profitSpark, sparkFormat: undefined, average: perDay(current.rpt_tf_profit_usd), description: "Terafort reported gross profit for the selected period." },
    // Profit % gets a sparkline (daily margin) but NO "Avg / day" on purpose. The mean of
    // the daily margins gives a $10 day the same weight as a $100,000 day, and total
    // profit / total revenue is already the headline figure - either number would be
    // repeating something or quietly misleading.
    { label: "Profit %", field: "rpt_profit_margin", value: formatPercent(profitPct), current: profitPct, previous: profitPctPrev, spark: marginSpark.length > 1 ? marginSpark : undefined, sparkFormat: (value: number) => formatPercent(value), average: undefined, description: "Reported profit as a percentage of reported gross revenue." },
  ];'''

OLD_JSX = '''              spark={kpi.spark}
              sparkDates={sparkDates}
              description={kpi.description}'''

NEW_JSX = '''              spark={kpi.spark}
              sparkDates={sparkDates}
              sparkFormat={kpi.sparkFormat}
              average={kpi.average}
              description={kpi.description}'''


def patch_row() -> None:
    source = ROW.read_text(encoding="utf-8") if ROW.exists() else None
    if source is None:
        fail(f"missing: {ROW.relative_to(ROOT)}")
        return
    if "perDay" in source:
        note("kpi-row.tsx already computes the daily average - left as is.")
        return
    out: str | None = source
    for old, new, what in (
        (OLD_MARGIN_PREV, NEW_MARGIN_PREV, "daily margin series + day count + perDay"),
        (OLD_KPIS, NEW_KPIS, "cards carry an average and Profit % gets a sparkline"),
        (OLD_JSX, NEW_JSX, "average and sparkFormat passed through"),
    ):
        if out is None:
            return
        out = swap(ROW, out, old, new, what)
    if out is None:
        return
    writes[ROW] = add_import(
        out, 'import { differenceInCalendarDays, parseISO } from "date-fns";'
    )


# ═══════════════════════════════════════════ B. pod table -> pod owner ═══════
POD_TABLE_SOURCE = '''"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import {
  type ColumnDef,
  METRIC_COLUMNS,
  MetricTable,
  type Row,
  permittedMeasures,
} from "@/components/overview/revenue-table";
import { usePodOwnerPerformance, useMe } from "@/lib/api-hooks";
import { UNASSIGNED_LABEL } from "@/lib/attribution";
import type { Filters } from "@/lib/filters";

/** The person a row belongs to.
 *
 *  An owner-less row is a real state, not a gap: apps in the unassigned pod (-1) and
 *  apps that have just arrived in the feed have nobody on them yet, and they carry real
 *  revenue. It is named rather than dropped so the totals still reconcile with the rest
 *  of the dashboard - and so the work of assigning them stays visible. */
function ownerKey(row: Row): string {
  const value = row.pod_owner;
  return value == null || String(value).trim() === "" ? UNASSIGNED_LABEL : String(value);
}

/** The identity column: the pod owner, linked to their own page.
 *
 *  Unassigned is deliberately NOT a link. There is no person to open, and a link that
 *  lands on an empty page reads as a broken page rather than as an empty bucket. */
const OWNER_IDENTITY: ColumnDef = {
  id: "pod_owner",
  label: "Pod Owner",
  requires: [],
  align: "left",
  fmt: "text",
  value: ownerKey,
  render: (row) => {
    const name = ownerKey(row);
    if (name === UNASSIGNED_LABEL) {
      return (
        <span
          className="text-muted-foreground"
          title="Apps not assigned to anyone yet, and new apps from the feed"
        >
          {UNASSIGNED_LABEL}
        </span>
      );
    }
    return (
      <Link
        href={`/pod-owner/${encodeURIComponent(name)}`}
        className="font-medium text-[color:var(--color-accent)] hover:underline"
      >
        {name}
      </Link>
    );
  },
};

/** Pod Owner Performance - the HOU table grouped by the person who owns the apps.
 *  ADMIN ONLY.
 *
 *  Grouped by OWNER rather than by pod (owner decision): one row per person, so someone
 *  who owns two pods reads as one line rather than two that have to be added up by eye.
 *
 *  The gate is server-side: the data comes from the admin router, which carries
 *  require_capability("admin_panel"). Returning null here is the cosmetic half and a
 *  second line of defence only - the query is also disabled for a non-admin, so no
 *  request is even made. */
export function PodTable({ filters }: { filters: Filters }) {
  const { data: me } = useMe();
  const isAdmin = Boolean(me?.capabilities.includes("admin_panel"));
  const permitted = useMemo(() => permittedMeasures(me?.metric_groups ?? []), [me]);

  const columns = useMemo(
    () =>
      [OWNER_IDENTITY, ...METRIC_COLUMNS].filter((c) =>
        c.requires.every((m) => permitted.has(m)),
      ),
    [permitted],
  );

  // Rank options are the visible metric columns themselves - RBAC-filtered for free, and
  // a future METRIC_COLUMNS addition becomes an option here with no edit. The identity
  // column is excluded: ranking people alphabetically is not a ranking anyone wants.
  const rankOptions = columns.filter((c) => c.id !== OWNER_IDENTITY.id);
  const [rankBy, setRankBy] = useState<string>("gross");
  // A saved choice can outlive the role that could see it; fall back rather than sorting
  // by nothing.
  const activeRank = rankOptions.find((c) => c.id === rankBy) ?? rankOptions[0];

  const measures = useMemo(
    () => [...new Set(columns.flatMap((c) => c.requires))],
    [columns],
  );

  const query = usePodOwnerPerformance(filters, measures, isAdmin);
  const rows = useMemo<Row[]>(() => (query.data?.rows ?? []) as Row[], [query.data]);

  // Once /me has resolved and the caller is not an admin, render nothing at all. Checked
  // against `me` rather than bare isAdmin so the card does not flicker away and back
  // while the profile is still loading.
  if (me && !isAdmin) return null;

  return (
    <MetricTable
      title="Pod Owner Performance"
      columns={columns}
      rows={rows}
      rowKey={ownerKey}
      isLoading={query.isLoading}
      isError={query.isError}
      sortId={activeRank?.id}
      action={
        rankOptions.length > 1 ? (
          <select
            aria-label="Rank pod owners by"
            value={activeRank?.id ?? ""}
            onChange={(event) => setRankBy(event.target.value)}
            className="h-8 rounded-[var(--radius-inner)] border border-input bg-background px-2 text-xs outline-none focus:ring-1 focus:ring-ring"
          >
            {rankOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        ) : undefined
      }
    />
  );
}
'''

# Fingerprints of the file this rewrite is based on. If any is absent the file is not the
# one that was read, and a wholesale rewrite would silently discard someone else's work.
POD_TABLE_FINGERPRINTS = (
    "export function PodTable",
    "usePodPerformance",
    "POD_IDENTITY",
    "OWNER_COLUMN",
    'title="Pod Performance"',
)


def patch_pod_table() -> None:
    source = POD_TABLE.read_text(encoding="utf-8") if POD_TABLE.exists() else None
    if source is None:
        fail(f"missing: {POD_TABLE.relative_to(ROOT)}")
        return
    if "usePodOwnerPerformance" in source:
        note("pod-table.tsx already keys on the owner - left as is.")
        return
    absent = [f for f in POD_TABLE_FINGERPRINTS if f not in source]
    if absent:
        fail(f"pod-table.tsx does not look like the file this rewrite was built from "
             f"(missing {absent}) - refusing to overwrite it.")
        return
    writes[POD_TABLE] = POD_TABLE_SOURCE
    note("  pod-table.tsx: rewritten to group by pod owner, each owner linked")


# ── the standalone pod-owner table gets the same link ────────────────────────
OLD_OWNER_RENDER = '''  render: (row) => {
    const key = ownerKey(row);
    return key === UNASSIGNED ? (
      <span className="text-muted-foreground">{UNASSIGNED}</span>
    ) : (
      <span className="font-medium">{key}</span>
    );
  },'''

NEW_OWNER_RENDER = '''  render: (row) => {
    const key = ownerKey(row);
    return key === UNASSIGNED ? (
      <span className="text-muted-foreground">{UNASSIGNED}</span>
    ) : (
      <Link
        href={`/pod-owner/${encodeURIComponent(key)}`}
        className="font-medium text-[color:var(--color-accent)] hover:underline"
      >
        {key}
      </Link>
    );
  },'''

OLD_OWNER_COMMENT = '''/** The identity column: the pod owner's name. No link — unlike HOU there is no per-person
 *  analytics page, and inventing one would imply a drill-down that does not exist. */'''

NEW_OWNER_COMMENT = '''/** The identity column: the pod owner's name, linked to their own page.
 *
 *  It used to say there was no per-person page and that inventing one would imply a
 *  drill-down that did not exist. There is one now (/pod-owner/[owner]), so the link is
 *  real. Unassigned stays unlinked: there is no person behind it. */'''


def patch_owner_table() -> None:
    source = OWNER_TABLE.read_text(encoding="utf-8") if OWNER_TABLE.exists() else None
    if source is None:
        fail(f"missing: {OWNER_TABLE.relative_to(ROOT)}")
        return
    if "/pod-owner/${" in source:
        note("pod-owner-table.tsx already links each owner - left as is.")
        return
    out = swap(OWNER_TABLE, source, OLD_OWNER_RENDER, NEW_OWNER_RENDER, "owner name links out")
    if out is None:
        return
    out = swap_comment(OWNER_TABLE, out, OLD_OWNER_COMMENT, NEW_OWNER_COMMENT,
                       "comment no longer claims there is no per-person page")
    writes[OWNER_TABLE] = add_import(out, 'import Link from "next/link";')


# ── the drill page ───────────────────────────────────────────────────────────
DETAIL_SOURCE = '''"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { MonthlyTrend } from "@/components/overview/monthly-trend";
import { RevenueVsSpend } from "@/components/overview/revenue-vs-spend";
import {
  type ColumnDef,
  METRIC_COLUMNS,
  MetricTable,
  type Row,
  permittedMeasures,
} from "@/components/overview/revenue-table";
import { Card, CardContent } from "@/components/ui/card";
import { useMe, usePodPerformance, useSummary } from "@/lib/api-hooks";
import { podLabel } from "@/lib/attribution";
import { formatPercent, formatUSD } from "@/lib/format";
import { useFilters } from "@/lib/use-filters";

/** One pod belonging to this owner. -1 reads as Unassigned, same as everywhere else. */
const POD_IDENTITY: ColumnDef = {
  id: "pod",
  label: "Pod",
  requires: [],
  align: "left",
  fmt: "text",
  value: (row) => podLabel(row.pod),
  render: (row) => <span className="font-medium">{podLabel(row.pod)}</span>,
};

function usd(value: number | null | undefined): string {
  return value == null ? "-" : formatUSD(value);
}

/** Everything one pod owner is responsible for, over the dashboard's current date range.
 *
 *  Reached from the Pod Owner tables, which are admin-only. This page does NOT claim to
 *  be a new gate: the totals come from /metrics/summary with a pod_owner filter, and that
 *  filter is already part of the global filter bar - anyone could narrow the whole
 *  dashboard to one owner today. What IS admin-only is the per-pod table below, which
 *  comes from the admin router, so it is hidden for everyone else rather than erroring.
 *
 *  Row scope still applies on top, server-side, as everywhere else. */
export default function PodOwnerDetailPage() {
  const params = useParams();
  const owner = decodeURIComponent(String(params.owner ?? ""));
  const { filters } = useFilters();
  const { data: me } = useMe();
  const isAdmin = Boolean(me?.capabilities.includes("admin_panel"));

  // Narrowing only - never widens, so it stays inside the caller's scope.
  const scoped = useMemo(() => ({ ...filters, podOwners: [owner] }), [filters, owner]);
  const summary = useSummary(scoped);
  const current = summary.data?.current ?? {};

  const permitted = useMemo(() => permittedMeasures(me?.metric_groups ?? []), [me]);
  const columns = useMemo(
    () =>
      [POD_IDENTITY, ...METRIC_COLUMNS].filter((c) =>
        c.requires.every((m) => permitted.has(m)),
      ),
    [permitted],
  );
  const measures = useMemo(() => [...new Set(columns.flatMap((c) => c.requires))], [columns]);
  const pods = usePodPerformance(scoped, measures, isAdmin);
  const podRows = useMemo<Row[]>(() => (pods.data?.rows ?? []) as Row[], [pods.data]);

  const margin =
    current.rpt_tf_profit_usd == null ||
    current.rpt_gross_revenue_usd == null ||
    current.rpt_gross_revenue_usd === 0
      ? undefined
      : current.rpt_tf_profit_usd / current.rpt_gross_revenue_usd;

  const tiles: { label: string; value: string }[] = [
    { label: "Revenue", value: usd(current.rpt_gross_revenue_usd) },
    { label: "UA Cost", value: usd(current.rpt_ua_cost_usd) },
    { label: "Partners Share, Fees & Taxes", value: usd(current.rpt_shares_fees_taxes_usd) },
    { label: "TF Profit", value: usd(current.rpt_tf_profit_usd) },
    { label: "Profit %", value: margin == null ? "-" : formatPercent(margin) },
    { label: "Ad Revenue", value: usd(current.total_ad_revenue_usd) },
    { label: "IAP Revenue", value: usd(current.total_iap_net_usd) },
    {
      label: "Installs",
      value:
        current.store_total_installs == null
          ? "-"
          : Math.round(Number(current.store_total_installs)).toLocaleString(),
    },
  ];

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <Link
          href="/overview"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Overview
        </Link>
        <h1 className="font-display text-2xl">
          Pod Owner - <span className="text-[color:var(--color-accent)]">{owner}</span>
        </h1>
        <p className="text-sm text-muted-foreground">
          Everything attributed to this owner across the selected date range. Attribution is
          resolved live from App Master, so a reassignment moves the whole history at once.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map((tile) => (
          <Card key={tile.label}>
            <CardContent className="py-4">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {tile.label}
              </p>
              <p className="mt-1 font-display text-2xl leading-none tabular-nums">
                {summary.isLoading ? "…" : tile.value}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <MonthlyTrend filters={scoped} />
        <RevenueVsSpend filters={scoped} />
      </div>

      {/* Admin-only, because the endpoint behind it is. Hidden rather than shown erroring. */}
      {isAdmin && (
        <MetricTable
          title={`Pods owned by ${owner}`}
          columns={columns}
          rows={podRows}
          rowKey={(row) => podLabel(row.pod)}
          isLoading={pods.isLoading}
          isError={pods.isError}
        />
      )}
    </div>
  );
}
'''


def patch_detail() -> None:
    if DETAIL.exists() and DETAIL.read_text(encoding="utf-8") == DETAIL_SOURCE:
        note("pod-owner detail page already present - left as is.")
        return
    writes[DETAIL] = DETAIL_SOURCE
    note(f"  {DETAIL.relative_to(ROOT)}: pod-owner detail page")


def main() -> int:
    note("KPI cards:")
    patch_card()
    patch_row()
    note("Pod owner:")
    patch_pod_table()
    patch_owner_table()
    patch_detail()

    if problems:
        report()
        return 1
    for path, text in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    report()
    return 0


def report() -> None:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED - nothing was written:")
        for line in problems:
            print(f"  - {line}")
    else:
        print(f"\nPATCHED {len(writes)} file(s). Verified only by:")
        print("  ./scripts/run-frontend-tests.sh")


if __name__ == "__main__":
    raise SystemExit(main())

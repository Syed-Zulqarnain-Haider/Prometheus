#!/usr/bin/env python3
"""Feature 8: a phone-first "Today" screen.

The dashboard is built for a desk. On a phone - which is where the app now installs, and
where most people actually check in - the useful question is much smaller: what happened
yesterday, what moved, is anything wrong, are we on track. Answering it currently means
loading the Executive Overview, waiting for a dozen widgets, and pinching around a grid.

/today is that question and nothing else, stacked in one column:

  1. The three headline numbers for the latest COMPLETE day, against the day before.
  2. What moved - the biggest contributors to the change, from /metrics/contribution.
  3. Anything unusual - per-app anomalies for the same day.
  4. Targets and budgets - the pacing board, compact.

Everything is composed from endpoints that already exist and already enforce RBAC, so
there is no new data path to secure. The one backend change is a genuinely missing field:
``/meta/freshness`` now reports ``latest_complete_date``. The concept already existed in
three services (alerts, digest, anomalies) and nowhere in the API, so every client that
wanted "which day is the data actually about" had to guess - and the honest answer is not
MAX(date), which is a partial day while Apple's numbers are still landing.

The global filter bar is hidden here on purpose. Today is a fixed window - the latest
complete day - and a date picker that silently does nothing would be worse than none.

Anchored: every anchor must appear EXACTLY once or NOTHING is written - all files
validate before any is touched. Idempotent. No migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

PAGE = Path("frontend/app/(app)/today/page.tsx")
CLIENT_COMPONENT = Path("frontend/components/today/today-client.tsx")

META = Path("backend/app/api/v1/meta.py")
TEST_METRICS = Path("backend/tests/test_metrics_api.py")
TYPES = Path("frontend/lib/types.ts")
NAV = Path("frontend/lib/nav.ts")
APP_LAYOUT = Path("frontend/app/(app)/layout.tsx")

PAGE_SOURCE = '''import { Suspense } from "react";

import { TodayClient } from "@/components/today/today-client";
import { Skeleton } from "@/components/ui/skeleton";

export default function TodayPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <TodayClient />
    </Suspense>
  );
}
'''

CLIENT_SOURCE = r'''"use client";

import { AlertTriangle, ArrowDownRight, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAnomalies,
  useContribution,
  useFreshness,
  usePacingBoard,
  useSummary,
} from "@/lib/api-hooks";
import { defaultFilters, type Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";
import type { ContributionRow, PacingRow } from "@/lib/types";

/* The phone screen.
 *
 * The desktop dashboard answers everything; this answers the four things anyone actually
 * checks on a phone - what happened, what moved it, is anything wrong, are we on track -
 * in one column, with no grid to pinch around.
 *
 * The day shown is the latest COMPLETE one, not the newest row in the table. Apple's data
 * lags two to three days, so the newest date is routinely a fraction of a real day and
 * showing it would report a collapse every single morning. */

const METRIC = "rpt_gross_revenue_usd";

const HEADLINES = [
  { field: "rpt_gross_revenue_usd", label: "Revenue" },
  { field: "rpt_ua_cost_usd", label: "Spend" },
  { field: "rpt_tf_profit_usd", label: "Gross profit" },
] as const;

function delta(current?: number | null, previous?: number | null): number | null {
  if (current == null || previous == null || previous === 0) return null;
  return (current - previous) / Math.abs(previous);
}

function Tile({
  label,
  value,
  change,
}: {
  label: string;
  value: number | null | undefined;
  change: number | null;
}) {
  const color =
    change == null
      ? "var(--color-text-muted)"
      : change >= 0
        ? "var(--color-positive)"
        : "var(--color-negative)";
  return (
    <Card>
      <CardContent className="p-3">
        <p className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          {label}
        </p>
        <p className="mt-0.5 text-lg font-semibold tabular-nums">
          {formatUSD(value, { compact: true })}
        </p>
        <p className="text-xs tabular-nums" style={{ color }}>
          {change == null ? "—" : `${change >= 0 ? "+" : ""}${formatPercent(change, 0)}`}
          <span className="ml-1 text-[var(--color-text-muted)]">vs prior day</span>
        </p>
      </CardContent>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h2 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
        {title}
      </h2>
      {children}
    </section>
  );
}

function MoverLine({ row, up }: { row: ContributionRow; up: boolean }) {
  const color = up ? "var(--color-positive)" : "var(--color-negative)";
  return (
    <li className="flex items-center gap-2 py-1.5">
      {up ? (
        <ArrowUpRight className="h-3.5 w-3.5 shrink-0" style={{ color }} />
      ) : (
        <ArrowDownRight className="h-3.5 w-3.5 shrink-0" style={{ color }} />
      )}
      <span className="min-w-0 flex-1 truncate text-sm">{row.label ?? "Unattributed"}</span>
      <span className="shrink-0 text-sm font-semibold tabular-nums" style={{ color }}>
        {up ? "+" : "−"}
        {formatUSD(Math.abs(row.delta), { compact: true })}
      </span>
    </li>
  );
}

function PacingLine({ row }: { row: PacingRow }) {
  const ahead = (row.pace_pct ?? 1) >= 1;
  const good = ahead === row.higher_is_better;
  const color = good ? "var(--color-positive)" : "var(--color-negative)";
  return (
    <li className="flex items-center gap-2 py-1.5">
      <span className="min-w-0 flex-1 truncate text-sm">
        {row.label}
        <span className="ml-1.5 text-[10px] uppercase text-[var(--color-text-muted)]">
          {row.kind === "revenue" ? "goal" : "budget"}
        </span>
      </span>
      <span className="shrink-0 text-sm font-semibold tabular-nums" style={{ color }}>
        {row.attainment_pct != null ? formatPercent(row.attainment_pct, 0) : "—"}
      </span>
    </li>
  );
}

export function TodayClient() {
  const freshness = useFreshness();
  const asOf = freshness.data?.latest_complete_date ?? null;

  // A single-day window, compared against the day before. Deliberately independent of the
  // global filter bar: Today is a fixed window, and a date picker that silently did
  // nothing would be worse than not having one.
  const dayFilters = useMemo<Filters>(() => {
    const base = defaultFilters();
    if (!asOf) return base;
    return { ...base, preset: "custom", dateFrom: asOf, dateTo: asOf, compare: true };
  }, [asOf]);

  const summary = useSummary(dayFilters);
  const movers = useContribution(dayFilters, "app", METRIC, 3);
  const anomalies = useAnomalies(dayFilters, "app", METRIC, 5);
  const now = new Date();
  const pacing = usePacingBoard(now.getFullYear(), now.getMonth() + 1);

  const current = summary.data?.current ?? {};
  const previous = summary.data?.previous ?? null;

  if (freshness.isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  if (!asOf) {
    return (
      <div className="space-y-4">
        <PageHeader title="Today" />
        <p className="text-sm text-[var(--color-text-muted)]">
          No complete day of data yet. The sync fills this in once a full day has landed.
        </p>
      </div>
    );
  }

  const gainers = movers.data?.gainers ?? [];
  const losers = movers.data?.losers ?? [];
  const unusual = anomalies.data?.rows ?? [];
  const pacingRows = pacing.data?.rows ?? [];

  return (
    <div className="mx-auto max-w-xl space-y-5 pb-8">
      <div>
        <PageHeader title="Today" />
        <p className="text-xs text-[var(--color-text-muted)]">
          The latest complete day: {asOf}. Apple&apos;s numbers lag two to three days, so
          the newest date in the table is usually still filling in.
        </p>
      </div>

      {summary.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {HEADLINES.map((headline) => (
            <Tile
              key={headline.field}
              label={headline.label}
              value={current[headline.field]}
              change={delta(current[headline.field], previous?.[headline.field])}
            />
          ))}
        </div>
      )}

      <Section title="What moved">
        {movers.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : gainers.length === 0 && losers.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            Nothing moved materially against the day before.
          </p>
        ) : (
          <ul className="divide-y rounded-[var(--radius-inner)] border px-3">
            {losers.map((row) => (
              <MoverLine key={`down-${row.key}`} row={row} up={false} />
            ))}
            {gainers.map((row) => (
              <MoverLine key={`up-${row.key}`} row={row} up />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Anything unusual">
        {anomalies.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : unusual.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            Nothing outside the last four weeks&apos; normal.
          </p>
        ) : (
          <ul className="divide-y rounded-[var(--radius-inner)] border px-3">
            {unusual.map((row) => {
              const color =
                row.direction === "up" ? "var(--color-positive)" : "var(--color-negative)";
              return (
                <li key={row.key ?? row.label} className="flex items-center gap-2 py-1.5">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0" style={{ color }} />
                  <Link
                    href={`/apps/${row.key}`}
                    className="min-w-0 flex-1 truncate text-sm hover:underline"
                  >
                    {row.label}
                  </Link>
                  <span
                    className="shrink-0 text-sm font-semibold tabular-nums"
                    style={{ color }}
                  >
                    {row.change_pct != null ? formatPercent(row.change_pct, 0) : "—"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section title="Targets & budgets">
        {pacing.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : pacingRows.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            No targets set for this month that you can see.
          </p>
        ) : (
          <ul className="divide-y rounded-[var(--radius-inner)] border px-3">
            {pacingRows.slice(0, 6).map((row) => (
              <PacingLine key={row.id} row={row} />
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
'''

# ── anchored edits ────────────────────────────────────────────────────────────
META_IMPORT_ANCHOR = "from app.services import admin_service, settings_service\n"
META_IMPORT_NEW = "from app.services import admin_service, day_completeness, settings_service\n"

META_ANCHOR = '''    return {
        "bq_built_at": last_success.bq_built_at.isoformat()
        if last_success and last_success.bq_built_at
        else None,
'''
META_NEW = '''    # Which DAY the data is actually about. Deliberately not MAX(date): the newest fact
    # date is routinely partial while Apple's numbers land, and a client that showed it
    # would report a collapse every morning. The concept already existed in three
    # services and nowhere in the API, so every caller had to guess.
    complete_day = await day_completeness.latest_complete_date(db)

    return {
        "bq_built_at": last_success.bq_built_at.isoformat()
        if last_success and last_success.bq_built_at
        else None,
        "latest_complete_date": complete_day.isoformat() if complete_day else None,
'''

TEST_ANCHOR = '''    assert body["rows_loaded"] == 100
'''
TEST_NEW = '''    assert body["rows_loaded"] == 100
    # Present on every response, even when no day is complete yet - a client that has to
    # branch on a missing key gets it wrong.
    assert "latest_complete_date" in body
'''

TYPES_ANCHOR = """export interface Freshness {
  bq_built_at: string | null;
  last_status: string | null;
  last_run_finished_at: string | null;
  rows_loaded: number | null;
}
"""
TYPES_NEW = """export interface Freshness {
  bq_built_at: string | null;
  /** The latest COMPLETE fact date - never MAX(date), which is a partial day while
   *  Apple's numbers are still landing. Null when no day has fully landed yet. */
  latest_complete_date: string | null;
  last_status: string | null;
  last_run_finished_at: string | null;
  rows_loaded: number | null;
}
"""

NAV_ICON_ANCHOR = "  LayoutDashboard,\n"
NAV_ICON_ADD = "  Sunrise,\n"
NAV_ITEM_ANCHOR = (
    '  { href: "/overview", label: "Executive Overview", icon: LayoutDashboard },\n'
)
NAV_ITEM_ADD = '  { href: "/today", label: "Today", icon: Sunrise },\n'

LAYOUT_ANCHOR = (
    '  const HIDE_FILTERS_ON = ["/app-master", "/admin", "/data-health", "/glossary", "/security"];\n'
)
LAYOUT_NEW = (
    "  // /today is a FIXED window (the latest complete day), so a date picker there would\n"
    "  // silently do nothing - worse than not having one.\n"
    '  const HIDE_FILTERS_ON = [\n'
    '    "/app-master",\n'
    '    "/admin",\n'
    '    "/data-health",\n'
    '    "/glossary",\n'
    '    "/security",\n'
    '    "/today",\n'
    "  ];\n"
)


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
    patched = [META, TEST_METRICS, TYPES, NAV, APP_LAYOUT]
    for path in patched:
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    # The screen composes the previous features' endpoints; without them it renders
    # empty sections and every fetch 404s.
    completeness = Path("backend/app/services/day_completeness.py")
    if not completeness.exists():
        die(f"{completeness} missing - run scripts/add-watchlist-anomalies.py first")
    if "usePacingBoard" not in Path("frontend/lib/api-hooks.ts").read_text():
        die("usePacingBoard missing - run scripts/add-scoped-targets-pacing.py first")

    texts = {path: path.read_text() for path in patched}

    plan: dict[Path, list[tuple[str, str, bool | None]]] = {}
    for path, marker, edits in (
        (
            META,
            "latest_complete_date",
            [(META_IMPORT_ANCHOR, META_IMPORT_NEW, None), (META_ANCHOR, META_NEW, None)],
        ),
        (TEST_METRICS, "latest_complete_date", [(TEST_ANCHOR, TEST_NEW, None)]),
        (TYPES, "latest_complete_date", [(TYPES_ANCHOR, TYPES_NEW, None)]),
        (
            NAV,
            '"/today"',
            [(NAV_ICON_ANCHOR, NAV_ICON_ADD, False), (NAV_ITEM_ANCHOR, NAV_ITEM_ADD, True)],
        ),
        (APP_LAYOUT, '"/today"', [(LAYOUT_ANCHOR, LAYOUT_NEW, None)]),
    ):
        edits_or_none = plan_edits(path, texts[path], marker, edits)
        if edits_or_none is not None:
            plan[path] = edits_or_none

    new_files = {PAGE: PAGE_SOURCE, CLIENT_COMPONENT: CLIENT_SOURCE}
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

    print("\nNo migration. /today is first in the sidebar and in the mobile nav (both read")
    print("NAV_ITEMS), so the installed PWA opens on it in one tap.")


if __name__ == "__main__":
    main()

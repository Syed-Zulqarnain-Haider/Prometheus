#!/usr/bin/env python3
"""The Overview headline row becomes the owner's Looker card set, with icons.

RE-ANCHORED against the deployed kpi-card.tsx after the first attempt refused to write.
That refusal was the script working: the card had grown three things this rewrite would
otherwise have DELETED - a 7-day moving average on the sparkline, per-day date tooltips,
and an "Avg / day" line under each figure. All three are preserved and passed through.

WHAT THE OWNER ASKED FOR
------------------------
"kpis like the looker" plus "icons in first page in executive overview page". The
screenshot shows eight cards - Total Installs, Ads Revenue, IAP, Gross Revenue, Tech Cost,
UA Cost, Net Revenue, ROAS. Tech Cost is dropped on the owner's instruction ("leave tech
cost we dont need that"), so seven ship.

EVERY DISPLAYED FIGURE COMES FROM THE SERVER
--------------------------------------------
gross_revenue_usd, net_revenue_usd and roas are computed by period_ratios.py (shipped by
derived-metrics.py, already live) with the same formula, rounding and RBAC gate the table
rows use - so a card and the column under it cannot disagree. Nothing here recomputes a
displayed number.

Two client-side derivations, both called out rather than buried:
  * a SPARKLINE SHAPE, because the timeseries endpoint serves registry columns and not
    derived ones, so the gross/net/ROAS lines are composed from their components. A
    sparkline carries no readable figure and the value beside it is the server's.
  * "Avg / day" = period total / days in the selected range, which is what the card
    already did. Deliberately NOT shown for ROAS: the mean of daily ratios weights a $10
    day like a $100,000 one, and period ROAS is already the headline figure - the same
    reasoning the previous card applied to Profit %.

A card whose metric the caller cannot see is DROPPED, not zeroed: the summary omits
measures outside the caller's metric groups, so a viewer sees the installs card and no
revenue at all, rather than a row of confident zeros.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
CARD = ROOT / "frontend/components/overview/kpi-card.tsx"
ROW = ROOT / "frontend/components/overview/kpi-row.tsx"
HELPERS = ROOT / "frontend/lib/kpi-definitions.ts"
TEST = ROOT / "frontend/tests/looker-kpis.test.ts"

report: list[str] = []

CARD_EDITS: list[tuple[str, str, str]] = [
    (
        "ReactNode import",
        'import { useMemo } from "react";',
        'import { useMemo, type ReactNode } from "react";',
    ),
    (
        "icon in the destructuring",
        "  description,\n  loading,\n}: {",
        "  description,\n  loading,\n  icon,\n}: {",
    ),
    (
        "icon in the props type",
        "  description?: string;\n  loading?: boolean;\n}) {",
        "  description?: string;\n  loading?: boolean;\n"
        "  /** Small leading glyph beside the label - decorative, never the only cue. */\n"
        "  icon?: ReactNode;\n}) {",
    ),
    (
        "icon rendered beside the label",
        (
            '          <span className="text-[11px] font-semibold uppercase '
            'tracking-[0.14em] text-muted-foreground">\n'
            "            <EditableTitle>{label}</EditableTitle>\n"
            "          </span>"
        ),
        (
            '          <span className="flex items-center gap-1.5 text-[11px] font-semibold '
            'uppercase tracking-[0.14em] text-muted-foreground">\n'
            "            {icon ? (\n"
            '              <span aria-hidden className="shrink-0 opacity-70">{icon}</span>\n'
            "            ) : null}\n"
            "            <EditableTitle>{label}</EditableTitle>\n"
            "          </span>"
        ),
    ),
]

HELPERS_SRC = '''\
/** The Overview headline cards: which server field each one reads, and how it reads.
 *
 * Separated from the component so the definitions can be tested without rendering
 * anything - the point of the list is WHICH FIELD each card shows, and that is exactly
 * what silently drifted before (three different "revenue" figures on one screen).
 *
 * Every `field` is served by /metrics/summary: the base measures come straight from the
 * metric registry, and gross_revenue_usd / net_revenue_usd / roas are computed
 * server-side in period_ratios.py under the same RBAC gate. Nothing here is arithmetic.
 */
export type KpiFormat = "usd" | "number" | "ratio";

export type KpiDef = {
  /** Field on summary.current - also the card's stable identity for renaming. */
  field: string;
  label: string;
  format: KpiFormat;
  /** Registry columns whose daily series compose this card's sparkline SHAPE. */
  sparkFrom: string[];
  description: string;
};

/** The owner's Looker card set, in the screenshot's reading order.
 *
 * Tech Cost is deliberately absent: "leave tech cost we dont need that" (owner). It is
 * still subtracted inside gross_profit_usd, which is a different, separate figure. */
export const LOOKER_KPIS: KpiDef[] = [
  {
    field: "store_total_installs",
    label: "Total Installs",
    format: "number",
    sparkFrom: ["store_total_installs"],
    description: "Store installs across every platform in the selected period.",
  },
  {
    field: "total_ad_revenue_usd",
    label: "Ads Revenue",
    format: "usd",
    sparkFrom: ["total_ad_revenue_usd"],
    description: "AdMob plus AppLovin. Mintegral publisher is excluded by design.",
  },
  {
    field: "total_iap_gross_usd",
    label: "IAP",
    format: "usd",
    sparkFrom: ["total_iap_gross_usd"],
    description: "In-app purchase revenue before refunds (gross).",
  },
  {
    field: "gross_revenue_usd",
    label: "Gross Revenue",
    format: "usd",
    sparkFrom: ["total_iap_gross_usd", "total_ad_revenue_usd"],
    description: "Ads plus IAP gross - before refunds and before spend.",
  },
  {
    field: "total_ua_spend_usd",
    label: "UA Cost",
    format: "usd",
    sparkFrom: ["total_ua_spend_usd"],
    description: "User-acquisition spend across every channel.",
  },
  {
    field: "net_revenue_usd",
    label: "Net Revenue",
    format: "usd",
    sparkFrom: ["total_revenue_usd", "total_ua_spend_usd"],
    description: "Revenue after refunds, less UA spend.",
  },
  {
    field: "roas",
    label: "ROAS",
    format: "ratio",
    sparkFrom: ["total_revenue_usd", "total_ua_spend_usd"],
    description: "Return on ad spend: revenue divided by UA spend for the period.",
  },
];

/** Every registry column the headline row needs one daily series of. */
export function sparkMetrics(defs: KpiDef[] = LOOKER_KPIS): string[] {
  return [...new Set(defs.flatMap((d) => d.sparkFrom))].sort();
}

/** Compose a sparkline SHAPE from its component series.
 *
 *  Shape only - never a displayed figure. One component: pass it through. Two: the
 *  second is subtracted for a difference card and divided for a ratio card, matching
 *  what the server computed for the value beside it. A ratio point with no denominator
 *  is null in the SHAPE - a gap in the line, never a drawn collapse to zero.
 */
export function composeSpark(series: number[][], format: KpiFormat): (number | null)[] {
  if (series.length === 0) return [];
  if (series.length === 1) return series[0];
  const [a, b] = series;
  const length = Math.min(a.length, b.length);
  const out: (number | null)[] = [];
  for (let i = 0; i < length; i += 1) {
    out.push(format === "ratio" ? (b[i] ? a[i] / b[i] : null) : a[i] - b[i]);
  }
  return out;
}

/** Does an "Avg / day" figure mean anything for this card?
 *
 *  Not for a ratio: the mean of daily ROAS weights a $10 day like a $100,000 one, and
 *  the period figure is already the headline. The same reasoning the card applied to
 *  Profit % before this change. */
export function hasDailyAverage(def: KpiDef): boolean {
  return def.format !== "ratio";
}

/** Cards whose metric the caller may see. A summary omits measures outside the caller's
 *  permitted groups, so an absent field means "not permitted", never "zero". */
export function visibleKpis(
  current: Record<string, unknown> | undefined,
  defs: KpiDef[] = LOOKER_KPIS,
): KpiDef[] {
  if (!current) return defs;
  return defs.filter((d) => d.field in current);
}
'''

ROW_SRC = '''"use client";

import { differenceInCalendarDays, parseISO } from "date-fns";
import {
  BadgeDollarSign,
  Coins,
  Download,
  Megaphone,
  ShoppingCart,
  TrendingUp,
  Wallet,
} from "lucide-react";
import type { ReactNode } from "react";

import { KpiCard } from "@/components/overview/kpi-card";
import { useSummary, useTimeseries } from "@/lib/api-hooks";
import { metricValues } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatNumber, formatPercent, formatUSD } from "@/lib/format";
import {
  composeSpark,
  hasDailyAverage,
  LOOKER_KPIS,
  sparkMetrics,
  visibleKpis,
  type KpiFormat,
} from "@/lib/kpi-definitions";

/** One icon per card, keyed by the field it shows. */
const ICONS: Record<string, ReactNode> = {
  store_total_installs: <Download className="h-3.5 w-3.5" />,
  total_ad_revenue_usd: <Megaphone className="h-3.5 w-3.5" />,
  total_iap_gross_usd: <ShoppingCart className="h-3.5 w-3.5" />,
  gross_revenue_usd: <Coins className="h-3.5 w-3.5" />,
  total_ua_spend_usd: <Wallet className="h-3.5 w-3.5" />,
  net_revenue_usd: <BadgeDollarSign className="h-3.5 w-3.5" />,
  roas: <TrendingUp className="h-3.5 w-3.5" />,
};

/** ROAS reads as a percentage on the owner's Looker sheet (127.29%), not as "1.27x". */
function render(value: unknown, format: KpiFormat): string {
  const n = typeof value === "number" ? value : null;
  if (format === "number") return formatNumber(n);
  if (format === "ratio") return formatPercent(n);
  return formatUSD(n);
}

/** How the sparkline tooltip formats a hovered point - matching the card's own units. */
function sparkFormatter(format: KpiFormat): ((value: number) => string) | undefined {
  if (format === "number") return (v: number) => formatNumber(v);
  if (format === "ratio") return (v: number) => formatPercent(v);
  return undefined; // USD is the card's default
}

export function KpiRow({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const timeseries = useTimeseries(filters, sparkMetrics(), "day");

  // One daily axis serves every card: each sparkline is a column of this same response.
  // The bucket is an ISO timestamp; the date part is all the tooltip needs.
  const sparkDates = (timeseries.data?.series ?? []).map((row) =>
    String(row.bucket ?? "").slice(0, 10),
  );

  const current = summary.data?.current as Record<string, number | null> | undefined;
  const previous = summary.data?.previous as Record<string, number | null> | null | undefined;
  const loading = summary.isLoading;

  // Days in the SELECTED RANGE, not the number of buckets that came back: a day with no
  // rows is still a day the average has to account for, and dividing by the rows present
  // would quietly inflate every figure whenever the feed is short.
  const days = (() => {
    const span =
      differenceInCalendarDays(parseISO(filters.dateTo), parseISO(filters.dateFrom)) + 1;
    return Number.isFinite(span) && span > 0 ? span : 0;
  })();

  /** The daily average of a period total, already formatted. */
  const perDay = (total: number | null | undefined, format: KpiFormat): string | undefined => {
    if (total == null || days === 0) return undefined;
    return format === "number"
      ? formatNumber(Math.round(total / days))
      : formatUSD(total / days, { compact: true });
  };

  // A card whose metric this caller cannot see is dropped, not zeroed: the summary omits
  // measures outside their permitted groups, so a viewer gets the installs card and no
  // revenue at all - rather than a confident row of zeros.
  const cards = visibleKpis(current, LOOKER_KPIS);

  return (
    <div className="space-y-4" data-tour="kpis">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
        {cards.map((kpi, index) => {
          const series = kpi.sparkFrom.map((m) => metricValues(timeseries.data, m));
          const value = current?.[kpi.field];
          return (
            <div
              key={kpi.field}
              className="anim-rise"
              style={{ animationDelay: `${0 + index * 60}ms` }}
            >
              <KpiCard
                label={kpi.label}
                icon={ICONS[kpi.field]}
                value={render(value, kpi.format)}
                current={value ?? undefined}
                previous={previous?.[kpi.field] ?? undefined}
                spark={composeSpark(series, kpi.format)}
                sparkDates={sparkDates}
                sparkFormat={sparkFormatter(kpi.format)}
                average={hasDailyAverage(kpi) ? perDay(value, kpi.format) : undefined}
                description={kpi.description}
                loading={loading}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
'''

TEST_SRC = '''import { describe, expect, it } from "vitest";

import {
  composeSpark,
  hasDailyAverage,
  LOOKER_KPIS,
  sparkMetrics,
  visibleKpis,
} from "@/lib/kpi-definitions";

/** The headline row is the owner's Looker card set. These tests pin WHICH FIELD each
 *  card reads - the thing that silently drifted into three different "revenue" figures
 *  on one screen - and that a card is hidden rather than zeroed when a caller may not
 *  see its metric. */
describe("Looker KPI definitions", () => {
  it("is the owner's card set, minus the tech cost they asked to drop", () => {
    expect(LOOKER_KPIS.map((k) => k.label)).toEqual([
      "Total Installs",
      "Ads Revenue",
      "IAP",
      "Gross Revenue",
      "UA Cost",
      "Net Revenue",
      "ROAS",
    ]);
    expect(LOOKER_KPIS.some((k) => /tech/i.test(k.label))).toBe(false);
  });

  it("reads gross revenue from the server's gross field, never the net one", () => {
    const gross = LOOKER_KPIS.find((k) => k.label === "Gross Revenue");
    expect(gross?.field).toBe("gross_revenue_usd");
    // The whole bug in one assertion: total_revenue_usd is the NET basis (IAP net +
    // ads), so a card labelled Gross must not read it.
    expect(gross?.field).not.toBe("total_revenue_usd");
  });

  it("shows ROAS as a percentage, matching the Looker sheet", () => {
    expect(LOOKER_KPIS.find((k) => k.label === "ROAS")?.format).toBe("ratio");
  });

  it("asks for each sparkline series exactly once", () => {
    const metrics = sparkMetrics();
    expect(new Set(metrics).size).toBe(metrics.length);
    expect(metrics).toContain("total_iap_gross_usd");
  });

  it("hides a card the caller may not see instead of showing zero", () => {
    const installsOnly = { store_total_installs: 946_800 };
    expect(visibleKpis(installsOnly).map((k) => k.label)).toEqual(["Total Installs"]);
    // Before the summary arrives, show the full set as skeletons - absence of data is
    // not absence of permission.
    expect(visibleKpis(undefined)).toHaveLength(LOOKER_KPIS.length);
  });

  it("composes a difference sparkline from its components", () => {
    expect(composeSpark([[100, 200], [40, 50]], "usd")).toEqual([60, 150]);
  });

  it("leaves a gap where a ratio has no denominator, rather than drawing zero", () => {
    // A day with no spend has no ROAS. Plotting 0 draws a collapse that did not happen.
    expect(composeSpark([[100, 50], [50, 0]], "ratio")).toEqual([2, null]);
  });

  it("passes a single-component sparkline straight through", () => {
    expect(composeSpark([[1, 2, 3]], "usd")).toEqual([1, 2, 3]);
  });

  it("offers no daily average for a ratio", () => {
    // The mean of daily ROAS weights a $10 day like a $100,000 one - the same reason
    // the card never showed one for Profit %.
    const roas = LOOKER_KPIS.find((k) => k.label === "ROAS")!;
    const revenue = LOOKER_KPIS.find((k) => k.label === "Gross Revenue")!;
    expect(hasDailyAverage(roas)).toBe(false);
    expect(hasDailyAverage(revenue)).toBe(true);
  });
});
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 12)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def main() -> int:
    if not CARD.exists() or not ROW.exists():
        print(f"ABORTED: missing {CARD} or {ROW}", file=sys.stderr)
        return 1

    card = CARD.read_text()
    if "icon?: ReactNode" in card:
        report.append("[card] icon prop already present - left alone")
    else:
        problems = [
            f"  [{label}] expected exactly 1 match, found {card.count(old)}\n"
            + window(CARD, old.splitlines()[0].strip()[:56])
            for label, old, _ in CARD_EDITS
            if card.count(old) != 1
        ]
        if problems:
            print("NOTHING WAS WRITTEN - the KPI row needs the icon prop to typecheck, so")
            print("the card and the row go together. Mismatches:\n")
            for p in problems:
                print(p)
            return 1
        for _, old, new in CARD_EDITS:
            card = card.replace(old, new, 1)
        CARD.write_text(card)
        report.append(f"[card] {CARD}: optional icon beside the label")

    HELPERS.write_text(HELPERS_SRC)
    report.append(f"[defs] {HELPERS}: the card set, testable without rendering")
    ROW.write_text(ROW_SRC)
    report.append(f"[row] {ROW}: seven Looker cards, every figure server-computed")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: nine cases pinning which field each card reads")

    print("PATCHED, NOT YET VERIFIED - tsc + vitest are the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(
        "\nThe card's moving average, date tooltips and Avg/day are PRESERVED and passed"
        "\nthrough - the first attempt would have deleted them, which is why it refused."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

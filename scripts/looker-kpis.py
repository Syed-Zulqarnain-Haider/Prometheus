#!/usr/bin/env python3
"""The Overview headline row becomes the owner's Looker card set, with icons.

WHAT THE OWNER ASKED FOR, AND WHAT THE SCREENSHOT SETTLED
---------------------------------------------------------
"kpis like the looker" plus "icons in first page in executive overview page". The
screenshot shows eight cards - Total Installs, Ads Revenue, IAP, Gross Revenue, Tech
Cost, UA Cost, Net Revenue, ROAS - each with a value, a delta against the comparison
period, and a sparkline. Tech Cost is dropped on the owner's instruction ("leave tech
cost we dont need that"), so seven ship.

EVERY DISPLAYED FIGURE COMES FROM THE SERVER
--------------------------------------------
gross_revenue_usd, net_revenue_usd and roas are computed by period_ratios.py (see
derived-metrics.py) with the same formula, rounding and RBAC gate the tables use - so a
card and the column under it cannot disagree. Nothing here recomputes a displayed number.

The one client-side derivation is a SPARKLINE SHAPE: the timeseries endpoint serves
registry columns, not derived ones, so the gross/net/ROAS trend lines are assembled from
their component series. A sparkline carries no readable figure - it is a shape - and the
value beside it is the server's. Called out here rather than buried, because "computed in
TypeScript" is exactly the drift the rest of this batch removes.

A card whose metric the caller cannot see is DROPPED, not zeroed: the summary omits
measures outside the caller's metric groups, so a viewer sees the installs card and no
revenue at all, rather than a row of confident zeros.

The card gains an optional icon. That is the only change to kpi-card.tsx - two anchored
edits, the props type and the destructuring, both of which report loudly and write
nothing if the deployed file has moved.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
CARD = ROOT / "frontend/components/overview/kpi-card.tsx"
ROW = ROOT / "frontend/components/overview/kpi-row.tsx"
TEST = ROOT / "frontend/tests/looker-kpis.test.ts"
HELPERS = ROOT / "frontend/lib/kpi-definitions.ts"

report: list[str] = []

CARD_EDITS = [
    (
        "icon in the props type",
        """  spark?: number[];
  loading?: boolean;
  description?: string;
}) {""",
        """  spark?: number[];
  loading?: boolean;
  description?: string;
  icon?: ReactNode;
}) {""",
    ),
    (
        "icon in the destructuring",
        """  spark,
  loading,
  description,
}: {""",
        """  spark,
  loading,
  description,
  icon,
}: {""",
    ),
    (
        "icon rendered beside the label",
        (
            '        <div className="text-[11px] font-semibold uppercase '
            'tracking-[0.14em] text-muted-foreground">\n'
            "          {label}\n"
            "        </div>"
        ),
        (
            '        <div className="flex items-center gap-1.5 text-[11px] '
            'font-semibold uppercase tracking-[0.14em] text-muted-foreground">\n'
            "          {icon ? <span aria-hidden "
            'className="text-muted-foreground/70">{icon}</span> : null}\n'
            "          {label}\n"
            "        </div>"
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
 *  is 0 in the SHAPE (the line simply sits on the floor there); the ratio VALUE stays
 *  null, which is what the card renders.
 */
export function composeSpark(series: number[][], format: KpiFormat): number[] {
  if (series.length === 0) return [];
  if (series.length === 1) return series[0];
  const [a, b] = series;
  const length = Math.min(a.length, b.length);
  const out: number[] = [];
  for (let i = 0; i < length; i += 1) {
    out.push(format === "ratio" ? (b[i] ? a[i] / b[i] : 0) : a[i] - b[i]);
  }
  return out;
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

export function KpiRow({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const timeseries = useTimeseries(filters, sparkMetrics(), "day");

  const current = summary.data?.current as Record<string, number | null> | undefined;
  const previous = summary.data?.previous as Record<string, number | null> | null | undefined;
  const loading = summary.isLoading;

  // A card whose metric this caller cannot see is dropped, not zeroed: the summary omits
  // measures outside their permitted groups, so a viewer gets the installs card and no
  // revenue at all - rather than a confident row of zeros.
  const cards = visibleKpis(current, LOOKER_KPIS);

  return (
    <div className="space-y-4" data-tour="kpis">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
        {cards.map((kpi) => {
          const series = kpi.sparkFrom.map((m) => metricValues(timeseries.data, m));
          return (
            <KpiCard
              key={kpi.field}
              label={kpi.label}
              icon={ICONS[kpi.field]}
              value={render(current?.[kpi.field], kpi.format)}
              current={current?.[kpi.field] ?? undefined}
              previous={previous?.[kpi.field] ?? undefined}
              spark={composeSpark(series, kpi.format)}
              description={kpi.description}
              loading={loading}
            />
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

  it("composes a ratio sparkline and puts a zero-denominator point on the floor", () => {
    expect(composeSpark([[100, 50], [50, 0]], "ratio")).toEqual([2, 0]);
  });

  it("passes a single-component sparkline straight through", () => {
    expect(composeSpark([[1, 2, 3]], "usd")).toEqual([1, 2, 3]);
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
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

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
        if "import type { ReactNode }" not in card:
            marker = '"use client";\n'
            react_import = 'import type { ReactNode } from "react";\n'
            if card.startswith(marker):
                card = card.replace(marker, marker + "\n" + react_import, 1)
            else:
                card = react_import + "\n" + card
        CARD.write_text(card)
        report.append(f"[card] {CARD}: optional icon beside the label")

    HELPERS.write_text(HELPERS_SRC)
    report.append(f"[defs] {HELPERS}: the card set, testable without rendering")
    ROW.write_text(ROW_SRC)
    report.append(f"[row] {ROW}: seven Looker cards, every figure server-computed")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: eight cases pinning which field each card reads")

    print("PATCHED, NOT YET VERIFIED - tsc + vitest are the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(
        "\nRequires derived-metrics.py to be deployed first: the Gross Revenue and Net"
        "\nRevenue cards read gross_revenue_usd / net_revenue_usd from /metrics/summary."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

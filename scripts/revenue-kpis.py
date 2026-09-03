#!/usr/bin/env python3
"""Compare KPIs on the Revenue page - "in revenue compare kpi as well".

The Overview has the Looker card row with period-over-period deltas when the global
Compare toggle is on. The Revenue page had charts and tables but no headline row at all, so
there was nothing for Compare to act on there. This adds a revenue-focused row of the SAME
KpiCard, driven by the same /metrics/summary call and the same global filters - so the
numbers cannot disagree with the Overview, and Compare works on it for free.

Seven cards, Looker order: Ads Revenue, IAP Revenue, Gross Revenue, UA Cost, Net Revenue,
ROAS, IAP ROAS. Gross, ROAS and IAP ROAS are the server-computed fields shipped by
derived-metrics; Net Revenue is total revenue minus UA cost (the owner's definition, tech
cost dropped). The card-building is a pure function in lib/ so it is unit-tested without
rendering anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
LIB = ROOT / "frontend/lib/revenue-kpis.ts"
COMPONENT = ROOT / "frontend/components/revenue/revenue-kpis.tsx"
CLIENT = ROOT / "frontend/components/revenue/revenue-client.tsx"
TEST = ROOT / "frontend/tests/revenue-kpis.test.ts"

LIB_SRC = '''import { formatPercent, formatUSD } from "@/lib/format";

/** One period's totals as /metrics/summary returns them. */
export type Totals = Record<string, number | null | undefined>;

export interface RevenueKpi {
  key: string;
  label: string;
  description: string;
  value: string;
  current: number | null;
  previous: number | null;
}

function num(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Net revenue = total revenue - UA cost. Tech cost is deliberately NOT subtracted. */
export function netRevenue(t: Totals): number | null {
  const revenue = num(t.total_revenue_usd);
  const spend = num(t.total_ua_spend_usd);
  return revenue === null || spend === null ? null : revenue - spend;
}

const NONE = "-";

/**
 * The Revenue page's headline row, Looker order. Pure: same inputs, same cards - which is
 * what lets a test pin it without rendering. `previous` is null unless Compare is on.
 */
export function revenueKpis(current: Totals, previous: Totals | null): RevenueKpi[] {
  const money = (key: string, label: string, description: string): RevenueKpi => {
    const cur = num(current[key]);
    return {
      key,
      label,
      description,
      value: cur === null ? NONE : formatUSD(cur),
      current: cur,
      previous: previous ? num(previous[key]) : null,
    };
  };
  const ratio = (key: string, label: string, description: string): RevenueKpi => {
    const cur = num(current[key]);
    return {
      key,
      label,
      description,
      value: cur === null ? NONE : formatPercent(cur, 2),
      current: cur,
      previous: previous ? num(previous[key]) : null,
    };
  };
  const net = netRevenue(current);
  return [
    money("total_ad_revenue_usd", "Ads Revenue", "AdMob + AppLovin"),
    money("total_iap_net_usd", "IAP Revenue", "In-app purchases, net of refunds"),
    money("gross_revenue_usd", "Gross Revenue", "IAP gross + ads revenue"),
    money("total_ua_spend_usd", "UA Cost", "User-acquisition spend"),
    {
      key: "net_revenue_usd",
      label: "Net Revenue",
      description: "Total revenue minus UA cost",
      value: net === null ? NONE : formatUSD(net),
      current: net,
      previous: previous ? netRevenue(previous) : null,
    },
    ratio("roas", "ROAS", "Total revenue / UA cost"),
    ratio("iap_roas", "IAP ROAS", "IAP net revenue / UA cost"),
  ];
}
'''

COMPONENT_SRC = '''"use client";

import { KpiCard } from "@/components/overview/kpi-card";
import { useSummary } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { revenueKpis } from "@/lib/revenue-kpis";

/**
 * The Revenue page's headline row. Same card, same summary call and same global filters as
 * the Overview, so the two pages cannot disagree - and the global Compare toggle drives the
 * period-over-period deltas here exactly as it does there.
 */
export function RevenueKpis({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const cards = revenueKpis(summary.data?.current ?? {}, summary.data?.previous ?? null);
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
      {cards.map((card) => (
        <KpiCard
          key={card.key}
          label={card.label}
          value={card.value}
          current={card.current ?? undefined}
          previous={card.previous ?? undefined}
          description={card.description}
          loading={summary.isLoading}
        />
      ))}
    </div>
  );
}
'''

TEST_SRC = '''import { describe, expect, it } from "vitest";

import { netRevenue, revenueKpis } from "@/lib/revenue-kpis";

const CURRENT = {
  total_ad_revenue_usd: 79_500,
  total_iap_net_usd: 26_800,
  gross_revenue_usd: 106_300,
  total_ua_spend_usd: 82_000,
  total_revenue_usd: 106_300,
  roas: 1.2729,
  iap_roas: 0.3268,
};

describe("revenueKpis", () => {
  it("renders the seven Looker cards in Looker order", () => {
    const keys = revenueKpis(CURRENT, null).map((c) => c.key);
    expect(keys).toEqual([
      "total_ad_revenue_usd",
      "total_iap_net_usd",
      "gross_revenue_usd",
      "total_ua_spend_usd",
      "net_revenue_usd",
      "roas",
      "iap_roas",
    ]);
  });

  it("net revenue is total revenue minus UA cost, with tech cost NOT subtracted", () => {
    expect(netRevenue(CURRENT)).toBeCloseTo(24_300, 6);
    expect(netRevenue({ ...CURRENT, tech_cost_usd: 1_480 })).toBeCloseTo(24_300, 6);
  });

  it("ROAS is a ratio shown as a percentage, like Looker's 127.29%", () => {
    const roas = revenueKpis(CURRENT, null).find((c) => c.key === "roas");
    expect(roas?.value).toBe("127.29%");
  });

  it("carries the previous period only when Compare supplies one", () => {
    const off = revenueKpis(CURRENT, null);
    expect(off.every((c) => c.previous === null)).toBe(true);

    const previous = { ...CURRENT, total_ad_revenue_usd: 70_000, total_ua_spend_usd: 80_000 };
    const on = revenueKpis(CURRENT, previous);
    expect(on.find((c) => c.key === "total_ad_revenue_usd")?.previous).toBe(70_000);
    // Net revenue's previous is DERIVED from the previous period, not copied from current.
    expect(on.find((c) => c.key === "net_revenue_usd")?.previous).toBeCloseTo(26_300, 6);
  });

  it("is null-safe: a missing measure is a dash, never NaN", () => {
    const cards = revenueKpis({}, null);
    expect(cards.every((c) => c.current === null && c.value === "-")).toBe(true);
    expect(netRevenue({ total_revenue_usd: 10 })).toBeNull();
  });
});
'''

EDITS: list[tuple[Path, str, str, str]] = [
    (
        CLIENT,
        "import the row",
        'import { useFilters } from "@/lib/use-filters";',
        'import { RevenueKpis } from "@/components/revenue/revenue-kpis";\n'
        'import { useFilters } from "@/lib/use-filters";',
    ),
    (
        CLIENT,
        "render it above the drill-down",
        "      <RevenueDrill key={drillKey} filters={filters} />",
        "      <RevenueKpis filters={filters} />\n"
        "      <RevenueDrill key={drillKey} filters={filters} />",
    ),
]


def main() -> int:
    if not CLIENT.exists():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1
    text = CLIENT.read_text()
    if "<RevenueKpis" in text:
        print("Already applied - left alone.")
        for path, src in ((LIB, LIB_SRC), (COMPONENT, COMPONENT_SRC), (TEST, TEST_SRC)):
            path.write_text(src)
            print(f"  - {path}: refreshed")
        return 0
    problems = [
        f"  [{label}] {path}: expected exactly 1 match, found {text.count(old)}"
        for path, label, old, _ in EDITS
        if text.count(old) != 1
    ]
    if problems:
        print("NOTHING WAS WRITTEN. Mismatches:\n" + "\n".join(problems))
        return 1
    for _, _, old, new in EDITS:
        text = text.replace(old, new, 1)
    CLIENT.write_text(text)
    LIB.write_text(LIB_SRC)
    COMPONENT.write_text(COMPONENT_SRC)
    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(TEST_SRC)
    print("PATCHED, NOT YET VERIFIED - tsc + vitest are the verification, not this script.")
    for path in (LIB, COMPONENT, CLIENT, TEST):
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

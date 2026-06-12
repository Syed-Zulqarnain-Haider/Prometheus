"use client";

import { Card, CardContent } from "@/components/ui/card";
import { DemoBadge } from "@/components/ui/demo-badge";
import { demoData } from "@/lib/demo-data";
import { SHOW_DEMO_WIDGETS } from "@/lib/demo-mode";
import { formatCompact, formatMultiplier, formatPercent, formatUSD } from "@/lib/format";

function DemoStat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {label}
          </span>
          <DemoBadge />
        </div>
        <div className="mt-2 font-display text-[length:var(--fs-stat)] leading-tight">
          {value}
        </div>
      </CardContent>
    </Card>
  );
}

/** Demo-only widgets (no real source yet). Rendered ONLY when the flag is on;
 *  every card carries a DEMO DATA badge. See docs/DESIGN.md §3. */
export function DemoSection() {
  if (!SHOW_DEMO_WIDGETS) return null;

  const stats = [
    { label: "Cash / Runway", value: `${formatUSD(demoData.cashRunway.cashUsd, { compact: true })} · ${demoData.cashRunway.runwayMonths}mo` },
    { label: "LTV", value: formatUSD(demoData.ltv.ltvUsd, { digits: 2 }) },
    { label: "Cohort ROAS D90", value: formatMultiplier(demoData.cohortRoas.d90) },
    { label: "Payback", value: `${demoData.payback.days}d` },
    { label: "DAU / MAU", value: `${formatCompact(demoData.dauMau.dau)} · ${formatPercent(demoData.dauMau.stickiness)}` },
    { label: "Retention D30", value: formatPercent(demoData.retention.d30) },
    { label: "Rating", value: `★ ${demoData.ratings.average}` },
  ];

  return (
    <section className="space-y-3">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Demo widgets (placeholder data)
      </h2>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7">
        {stats.map((stat) => (
          <DemoStat key={stat.label} label={stat.label} value={stat.value} />
        ))}
      </div>
    </section>
  );
}

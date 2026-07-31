"use client";

import { KpiCard } from "@/components/overview/kpi-card";
import { useSummary, useTimeseries } from "@/lib/api-hooks";
import { metricValues } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

// Reported-actual (rpt_*) measures drive the headline cards — the finance-authoritative
// figures. Each card's sparkline is the daily series of its own measure.
const SPARK_METRICS = [
  "rpt_gross_revenue_usd",
  "rpt_ua_cost_usd",
  "rpt_shares_fees_taxes_usd",
  "rpt_tf_profit_usd",
];

/** margin = profit / gross revenue, guarded like the server ratios (None on 0 denominator). */
function margin(profit?: number | null, revenue?: number | null): number | undefined {
  if (profit == null || revenue == null || revenue === 0) return undefined;
  return profit / revenue;
}

export function KpiRow({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const timeseries = useTimeseries(filters, SPARK_METRICS, "day");

  const current = summary.data?.current ?? {};
  const previous = summary.data?.previous ?? null;
  const loading = summary.isLoading;

  const revenueSpark = metricValues(timeseries.data, "rpt_gross_revenue_usd");
  const uaCostSpark = metricValues(timeseries.data, "rpt_ua_cost_usd");
  const sharesSpark = metricValues(timeseries.data, "rpt_shares_fees_taxes_usd");
  const profitSpark = metricValues(timeseries.data, "rpt_tf_profit_usd");

  // Profit % from the reported figures (computed client-side; both components are permitted
  // together, so it inherits the same RBAC as the profitability group).
  const profitPct = margin(current.rpt_tf_profit_usd, current.rpt_gross_revenue_usd);
  const profitPctPrev = margin(previous?.rpt_tf_profit_usd, previous?.rpt_gross_revenue_usd);

  const kpis = [
    { label: "Revenue", field: "rpt_gross_revenue_usd", value: formatUSD(current.rpt_gross_revenue_usd), current: current.rpt_gross_revenue_usd, previous: previous?.rpt_gross_revenue_usd, spark: revenueSpark, description: "Reported gross revenue for the selected period." },
    { label: "Spend", field: "rpt_ua_cost_usd", value: formatUSD(current.rpt_ua_cost_usd), current: current.rpt_ua_cost_usd, previous: previous?.rpt_ua_cost_usd, spark: uaCostSpark, description: "Reported user-acquisition cost for the selected period." },
    { label: "Partners Share, Fees & Taxes", field: "rpt_shares_fees_taxes_usd", value: formatUSD(current.rpt_shares_fees_taxes_usd), current: current.rpt_shares_fees_taxes_usd, previous: previous?.rpt_shares_fees_taxes_usd, spark: sharesSpark, description: "Partners' share plus fees and taxes for the selected period." },
    { label: "Gross Profit", field: "rpt_tf_profit_usd", value: formatUSD(current.rpt_tf_profit_usd), current: current.rpt_tf_profit_usd, previous: previous?.rpt_tf_profit_usd, spark: profitSpark, description: "Terafort reported gross profit for the selected period." },
    { label: "Profit %", field: "rpt_profit_margin", value: formatPercent(profitPct), current: profitPct, previous: profitPctPrev, spark: undefined, description: "Reported profit as a percentage of reported gross revenue." },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      {kpis.map((kpi) => (
        <KpiCard
          key={kpi.field}
          label={kpi.label}
          value={kpi.value}
          current={kpi.current}
          previous={kpi.previous}
          spark={kpi.spark}
          description={kpi.description}
          loading={loading}
        />
      ))}
    </div>
  );
}

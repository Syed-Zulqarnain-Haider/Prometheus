"use client";

import { KpiCard } from "@/components/overview/kpi-card";
import { useSummary, useTimeseries } from "@/lib/api-hooks";
import { metricValues } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

// Components needed to draw the sparklines for the headline + derived KPIs.
const SPARK_METRICS = [
  "total_revenue_usd",
  "total_ua_spend_usd",
  "total_iap_gross_usd",
  "total_ad_revenue_usd",
  "tech_cost_usd",
];

function elementwise(
  a: number[],
  b: number[],
  op: (x: number, y: number) => number,
): number[] {
  const length = Math.max(a.length, b.length);
  return Array.from({ length }, (_, i) => op(a[i] ?? 0, b[i] ?? 0));
}

export function KpiRow({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const timeseries = useTimeseries(filters, SPARK_METRICS, "day");

  const current = summary.data?.current ?? {};
  const previous = summary.data?.previous ?? null;
  const loading = summary.isLoading;

  // Derived sparklines, period-correct per bucket (mirrors the server KPI math).
  const revenue = metricValues(timeseries.data, "total_revenue_usd");
  const spend = metricValues(timeseries.data, "total_ua_spend_usd");
  const iapGross = metricValues(timeseries.data, "total_iap_gross_usd");
  const adRevenue = metricValues(timeseries.data, "total_ad_revenue_usd");
  const techCost = metricValues(timeseries.data, "tech_cost_usd");

  const netRevenueSpark = elementwise(revenue, spend, (r, s) => r - s);
  const grossProfitSpark = elementwise(
    elementwise(iapGross, adRevenue, (g, a) => g + a),
    elementwise(spend, techCost, (s, t) => s + t),
    (gross, costs) => gross - costs,
  );

  const kpis = [
    { label: "Revenue", field: "total_revenue_usd", value: formatUSD(current.total_revenue_usd), spark: revenue },
    { label: "Spend", field: "total_ua_spend_usd", value: formatUSD(current.total_ua_spend_usd), spark: spend },
    { label: "Net Revenue", field: "net_revenue_usd", value: formatUSD(current.net_revenue_usd), spark: netRevenueSpark },
    { label: "Gross Profit", field: "gross_profit_usd", value: formatUSD(current.gross_profit_usd), spark: grossProfitSpark },
    { label: "Profit %", field: "profit_margin", value: formatPercent(current.profit_margin), spark: undefined },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      {kpis.map((kpi) => (
        <KpiCard
          key={kpi.field}
          label={kpi.label}
          value={kpi.value}
          current={current[kpi.field]}
          previous={previous?.[kpi.field]}
          spark={kpi.spark}
          loading={loading}
        />
      ))}
    </div>
  );
}

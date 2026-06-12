"use client";

import { KpiCard } from "@/components/overview/kpi-card";
import { useSummary, useTimeseries } from "@/lib/api-hooks";
import { metricValues } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

const SPARK_METRICS = [
  "total_revenue_usd",
  "total_ua_spend_usd",
  "total_iap_net_usd",
  "profit_usd",
];

export function KpiRow({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const timeseries = useTimeseries(filters, SPARK_METRICS, "day");

  const current = summary.data?.current ?? {};
  const previous = summary.data?.previous ?? null;
  const loading = summary.isLoading;

  const kpis = [
    { label: "Revenue", field: "total_revenue_usd", value: formatUSD(current.total_revenue_usd), spark: true },
    { label: "Spend", field: "total_ua_spend_usd", value: formatUSD(current.total_ua_spend_usd), spark: true },
    { label: "Net IAP", field: "total_iap_net_usd", value: formatUSD(current.total_iap_net_usd), spark: true },
    { label: "Profit", field: "profit_usd", value: formatUSD(current.profit_usd), spark: true },
    { label: "Profit %", field: "profit_margin", value: formatPercent(current.profit_margin), spark: false },
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
          spark={kpi.spark ? metricValues(timeseries.data, kpi.field) : undefined}
          loading={loading}
        />
      ))}
    </div>
  );
}

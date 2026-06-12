"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

const NETWORKS = [
  { metric: "fb_spend_usd", label: "Facebook", color: "--chart-bar" },
  { metric: "gads_spend_usd", label: "Google Ads", color: "--chart-spark-cash" },
  { metric: "mint_adv_spend_usd", label: "Mintegral", color: "--color-amber" },
];

export function SpendByNetwork({ filters }: { filters: Filters }) {
  const ts = useTimeseries(
    filters,
    NETWORKS.map((n) => n.metric),
    "day",
  );
  const labels = bucketLabels(ts.data);
  const totalPoints = NETWORKS.reduce(
    (sum, n) => sum + metricValues(ts.data, n.metric).reduce((a, b) => a + b, 0),
    0,
  );

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: NETWORKS.map((n) => n.label) },
    tooltip: { trigger: "axis", valueFormatter: (v) => formatUSD(Number(v), { compact: true }) },
    xAxis: { type: "category", data: labels, boundaryGap: false },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series: NETWORKS.map((n) => ({
      name: n.label,
      type: "line",
      stack: "spend",
      data: metricValues(ts.data, n.metric),
      showSymbol: false,
      areaStyle: { color: token(n.color), opacity: 0.5 },
      lineStyle: { width: 1, color: token(n.color) },
    })),
  };

  return (
    <ChartCard title="Spend by Network">
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && totalPoints === 0}
        height={280}
      />
    </ChartCard>
  );
}

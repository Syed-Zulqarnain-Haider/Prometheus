"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

export function RevenueComposition({ filters }: { filters: Filters }) {
  const ts = useTimeseries(
    filters,
    ["total_iap_net_usd", "total_ad_revenue_usd"],
    "day",
  );
  const labels = bucketLabels(ts.data);
  const iap = metricValues(ts.data, "total_iap_net_usd");
  const ad = metricValues(ts.data, "total_ad_revenue_usd");
  const empty = iap.length === 0 && ad.length === 0;

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: ["IAP (net)", "Ad revenue"] },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => formatUSD(Number(v), { compact: true }),
    },
    xAxis: { type: "category", data: labels, boundaryGap: false },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series: [
      {
        name: "IAP (net)",
        type: "line",
        stack: "rev",
        data: iap,
        showSymbol: false,
        areaStyle: { color: token("--chart-grad-to"), opacity: 0.5 },
        lineStyle: { width: 1, color: token("--chart-grad-to") },
      },
      {
        name: "Ad revenue",
        type: "line",
        stack: "rev",
        data: ad,
        showSymbol: false,
        areaStyle: { color: token("--chart-grad-from"), opacity: 0.5 },
        lineStyle: { width: 1, color: token("--chart-grad-from") },
      },
    ],
  };

  return (
    <ChartCard title="Revenue Composition">
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && empty}
        height={280}
      />
    </ChartCard>
  );
}

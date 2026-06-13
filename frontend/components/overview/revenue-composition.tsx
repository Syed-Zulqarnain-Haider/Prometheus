"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { usePreviousTimeseries, useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

const METRICS = ["total_iap_net_usd", "total_ad_revenue_usd"];

export function RevenueComposition({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, METRICS, "day");
  const prev = usePreviousTimeseries(filters, METRICS, "day");
  const labels = bucketLabels(ts.data);
  const iap = metricValues(ts.data, "total_iap_net_usd");
  const ad = metricValues(ts.data, "total_ad_revenue_usd");
  const empty = iap.length === 0 && ad.length === 0;

  const prevIap = metricValues(prev.data, "total_iap_net_usd");
  const prevAd = metricValues(prev.data, "total_ad_revenue_usd");
  const prevTotal = prevIap.map((v, i) => v + (prevAd[i] ?? 0));
  const showGhost = filters.compare && prevTotal.length > 0;

  const legend = ["IAP (net)", "Ad revenue"];
  const series: EChartsOption["series"] = [
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
  ];
  if (showGhost) {
    legend.push("Total (prev)");
    series.push({
      name: "Total (prev)",
      type: "line",
      data: prevTotal,
      showSymbol: false,
      lineStyle: { type: "dashed", width: 1.5, color: token("--chart-target") },
      itemStyle: { color: token("--chart-target") },
      z: 3,
    });
  }

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: legend },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => formatUSD(Number(v), { compact: true }),
    },
    xAxis: { type: "category", data: labels, boundaryGap: false },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series,
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

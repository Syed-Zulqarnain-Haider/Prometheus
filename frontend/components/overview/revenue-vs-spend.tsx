"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { usePreviousTimeseries, useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

const METRICS = ["total_revenue_usd", "total_ua_spend_usd"];

export function RevenueVsSpend({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, METRICS, "day");
  const prev = usePreviousTimeseries(filters, METRICS, "day");
  const labels = bucketLabels(ts.data);
  const revenue = metricValues(ts.data, "total_revenue_usd");
  const spend = metricValues(ts.data, "total_ua_spend_usd");
  const profit = revenue.map((r, i) => r - (spend[i] ?? 0));
  const showGhost = filters.compare && (prev.data?.series.length ?? 0) > 0;
  const prevRevenue = metricValues(prev.data, "total_revenue_usd");
  const prevSpend = metricValues(prev.data, "total_ua_spend_usd");

  const legend = ["Revenue", "Spend", "Profit"];
  const series: EChartsOption["series"] = [
    {
      name: "Profit",
      type: "line",
      data: profit,
      showSymbol: false,
      lineStyle: { opacity: 0 },
      areaStyle: { color: token("--color-accent-soft"), opacity: 1 },
      z: 1,
    },
    {
      name: "Revenue",
      type: "line",
      data: revenue,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: token("--chart-spark") },
      itemStyle: { color: token("--chart-spark") },
      z: 3,
    },
    {
      name: "Spend",
      type: "line",
      data: spend,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: token("--chart-line-cpi") },
      itemStyle: { color: token("--chart-line-cpi") },
      z: 2,
    },
  ];
  if (showGhost) {
    legend.push("Revenue (prev)", "Spend (prev)");
    series.push(
      {
        name: "Revenue (prev)",
        type: "line",
        data: prevRevenue,
        showSymbol: false,
        lineStyle: { type: "dashed", width: 1.5, opacity: 0.6, color: token("--chart-spark") },
        itemStyle: { color: token("--chart-spark") },
        z: 2,
      },
      {
        name: "Spend (prev)",
        type: "line",
        data: prevSpend,
        showSymbol: false,
        lineStyle: { type: "dashed", width: 1.5, opacity: 0.6, color: token("--chart-line-cpi") },
        itemStyle: { color: token("--chart-line-cpi") },
        z: 2,
      },
    );
  }

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: legend },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => formatUSD(Number(v), { compact: true }),
    },
    xAxis: { type: "category", data: labels },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series,
  };

  return (
    <ChartCard title="Revenue vs Spend (profit shaded)">
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && revenue.length === 0}
        height={280}
      />
    </ChartCard>
  );
}

"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

export function SpendVsRevenue({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, ["total_ua_spend_usd", "total_revenue_usd"], "day");
  const labels = bucketLabels(ts.data);
  const spend = metricValues(ts.data, "total_ua_spend_usd");
  const revenue = metricValues(ts.data, "total_revenue_usd");
  const roas = spend.map((s, i) => (s > 0 ? Number((revenue[i] / s).toFixed(2)) : null));

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: ["Spend", "Revenue", "ROAS"] },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: labels },
    yAxis: [
      {
        type: "value",
        axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
      },
      {
        type: "value",
        name: "ROAS",
        position: "right",
        min: 0,
        splitLine: { show: false },
        axisLabel: { formatter: (v: number) => `${v}×` },
      },
    ],
    series: [
      {
        name: "Spend",
        type: "bar",
        yAxisIndex: 0,
        data: spend,
        itemStyle: { color: token("--chart-bar-2") },
        barMaxWidth: 18,
      },
      {
        name: "Revenue",
        type: "line",
        yAxisIndex: 0,
        data: revenue,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: token("--chart-spark") },
        itemStyle: { color: token("--chart-spark") },
      },
      {
        name: "ROAS",
        type: "line",
        yAxisIndex: 1,
        data: roas,
        showSymbol: false,
        lineStyle: { width: 1.5, color: token("--chart-line-cpi") },
        itemStyle: { color: token("--chart-line-cpi") },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", color: token("--chart-target") },
          label: { formatter: "Break-even", color: token("--color-text-secondary") },
          data: [{ yAxis: 1 }],
        },
      },
    ],
  };

  return (
    <ChartCard title="Spend vs Revenue (break-even ROAS = 1×)">
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && spend.length === 0 && revenue.length === 0}
        height={300}
      />
    </ChartCard>
  );
}

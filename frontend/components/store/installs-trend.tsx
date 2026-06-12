"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatCompact, formatNumber } from "@/lib/format";

export function InstallsTrend({ filters }: { filters: Filters }) {
  const ts = useTimeseries(
    filters,
    ["store_first_time_installs", "store_redownloads"],
    "day",
  );
  const labels = bucketLabels(ts.data);
  const firstTime = metricValues(ts.data, "store_first_time_installs");
  const redownloads = metricValues(ts.data, "store_redownloads");

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: ["First-time", "Redownloads"] },
    tooltip: { trigger: "axis", valueFormatter: (v) => formatNumber(Number(v)) },
    xAxis: { type: "category", data: labels, boundaryGap: false },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatCompact(v) } },
    series: [
      {
        name: "First-time",
        type: "line",
        stack: "installs",
        data: firstTime,
        showSymbol: false,
        areaStyle: { color: token("--chart-bar"), opacity: 0.5 },
        lineStyle: { width: 1, color: token("--chart-bar") },
      },
      {
        name: "Redownloads",
        type: "line",
        stack: "installs",
        data: redownloads,
        showSymbol: false,
        areaStyle: { color: token("--chart-spark-cash"), opacity: 0.5 },
        lineStyle: { width: 1, color: token("--chart-spark-cash") },
      },
    ],
  };

  return (
    <ChartCard title="Installs: First-time vs Redownloads">
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && firstTime.length === 0 && redownloads.length === 0}
        height={280}
      />
    </ChartCard>
  );
}

"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { usePreviousTimeseries, useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

export function MonthlyTrend({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, ["total_revenue_usd"], "month");
  const prev = usePreviousTimeseries(filters, ["total_revenue_usd"], "month");
  const labels = bucketLabels(ts.data);
  const values = metricValues(ts.data, "total_revenue_usd");
  const prevValues = metricValues(prev.data, "total_revenue_usd");
  const showGhost = filters.compare && prevValues.length > 0;

  const series: EChartsOption["series"] = [
    {
      name: "Revenue",
      type: "bar",
      data: values,
      itemStyle: { color: token("--chart-bar") },
      barMaxWidth: 28,
    },
  ];
  if (showGhost) {
    series.push({
      name: "Revenue (prev)",
      type: "line",
      data: prevValues,
      showSymbol: false,
      smooth: true,
      lineStyle: { type: "dashed", width: 1.5, color: token("--chart-target") },
      itemStyle: { color: token("--chart-target") },
      z: 3,
    });
  }

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: showGhost ? ["Revenue", "Revenue (prev)"] : ["Revenue"] },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => formatUSD(Number(v), { compact: true }),
    },
    xAxis: { type: "category", data: labels.map((d) => d.slice(0, 7)) },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series,
  };

  return (
    <ChartCard
      title="Monthly Revenue Trend"
      action={
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          Target line: set in Admin (Step 7)
        </span>
      }
    >
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && values.length === 0}
        height={260}
      />
    </ChartCard>
  );
}

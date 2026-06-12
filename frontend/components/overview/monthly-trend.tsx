"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

export function MonthlyTrend({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, ["total_revenue_usd"], "month");
  const labels = bucketLabels(ts.data);
  const values = metricValues(ts.data, "total_revenue_usd");

  const option: EChartsOption = {
    grid: { top: 16, bottom: 24, left: 8, right: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => formatUSD(Number(v), { compact: true }),
    },
    xAxis: {
      type: "category",
      data: labels.map((d) => d.slice(0, 7)),
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series: [
      {
        type: "bar",
        data: values,
        itemStyle: { color: token("--chart-bar") },
        barMaxWidth: 28,
      },
    ],
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

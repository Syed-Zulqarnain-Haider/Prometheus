"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useBreakdown } from "@/lib/api-hooks";
import { num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatCompact, formatUSD } from "@/lib/format";

interface ScatterPoint {
  value: [number, number];
  name: string;
  symbolSize: number;
}

export function CpiVolumeScatter({ filters }: { filters: Filters }) {
  const breakdown = useBreakdown(filters, "app", [
    "total_ua_spend_usd",
    "total_paid_installs",
  ]);
  const rows = breakdown.data?.rows ?? [];

  const points: ScatterPoint[] = rows
    .map((row) => {
      const installs = num(row.total_paid_installs);
      const spend = num(row.total_ua_spend_usd);
      const cpi = installs > 0 ? spend / installs : 0;
      return {
        value: [installs, Number(cpi.toFixed(2))] as [number, number],
        name: String(row.app_name ?? row.app ?? "—"),
        symbolSize: Math.max(8, Math.min(42, Math.sqrt(spend) / 4)),
      };
    })
    .filter((p) => p.value[0] > 0);

  const option: EChartsOption = {
    grid: { top: 16, bottom: 40, left: 8, right: 16, containLabel: true },
    tooltip: {
      trigger: "item",
      formatter: (p: unknown) => {
        const point = (p as { data: ScatterPoint }).data;
        return `${point.name}<br/>CPI ${formatUSD(point.value[1], { digits: 2 })}<br/>Installs ${formatCompact(point.value[0])}`;
      },
    },
    xAxis: {
      type: "value",
      name: "Paid installs",
      nameLocation: "middle",
      nameGap: 28,
      axisLabel: { formatter: (v: number) => formatCompact(v) },
    },
    yAxis: {
      type: "value",
      name: "CPI",
      axisLabel: { formatter: (v: number) => formatUSD(v, { digits: 2 }) },
    },
    series: [
      {
        type: "scatter",
        data: points,
        itemStyle: { color: token("--chart-bar"), opacity: 0.75 },
      },
    ],
  };

  return (
    <ChartCard title="CPI vs Install Volume (bubble = spend)">
      <Chart
        option={option}
        loading={breakdown.isLoading}
        error={breakdown.isError}
        isEmpty={!breakdown.isLoading && points.length === 0}
        height={300}
      />
    </ChartCard>
  );
}

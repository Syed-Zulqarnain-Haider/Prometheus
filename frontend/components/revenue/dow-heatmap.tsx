"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useTimeseries } from "@/lib/api-hooks";
import { num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function parseLocalDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

function mondayOf(date: Date): Date {
  const x = new Date(date);
  x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
}

export function DowHeatmap({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, ["total_revenue_usd"], "day");
  const series = ts.data?.series ?? [];

  let weeks = 0;
  let maxValue = 0;
  const data: [number, number, number][] = [];

  if (series.length > 0) {
    const dates = series.map((row) => parseLocalDate(String(row.bucket)));
    const anchor = mondayOf(dates[0]).getTime();
    const weekMs = 7 * 24 * 60 * 60 * 1000;
    series.forEach((row, i) => {
      const date = dates[i];
      const weekIndex = Math.round((mondayOf(date).getTime() - anchor) / weekMs);
      const dow = (date.getDay() + 6) % 7;
      const value = num(row.total_revenue_usd);
      data.push([weekIndex, dow, value]);
      weeks = Math.max(weeks, weekIndex + 1);
      maxValue = Math.max(maxValue, value);
    });
  }

  const weekLabels = Array.from({ length: weeks }, (_, i) => `W${i + 1}`);

  const option: EChartsOption = {
    grid: { top: 8, bottom: 56, left: 40, right: 8, containLabel: true },
    tooltip: {
      position: "top",
      formatter: (p: unknown) => {
        const params = p as { value: [number, number, number] };
        return `${DOW[params.value[1]]} · ${formatUSD(params.value[2])}`;
      },
    },
    xAxis: { type: "category", data: weekLabels, splitArea: { show: true } },
    yAxis: { type: "category", data: DOW, inverse: true, splitArea: { show: true } },
    visualMap: {
      min: 0,
      max: maxValue || 1,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      inRange: { color: [token("--color-bg-elevated"), token("--chart-bar")] },
      textStyle: { color: token("--color-text-secondary") },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: { show: false },
        emphasis: { itemStyle: { borderColor: token("--color-text-primary"), borderWidth: 1 } },
      },
    ],
  };

  return (
    <ChartCard title="Revenue by Day of Week">
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && data.length === 0}
        height={260}
      />
    </ChartCard>
  );
}

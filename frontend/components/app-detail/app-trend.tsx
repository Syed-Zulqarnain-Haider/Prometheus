"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatCompact, formatNumber, formatUSD } from "@/lib/format";

const COLORS = ["--chart-bar", "--chart-spark", "--chart-spark-cash", "--color-amber"];

interface MetricDef {
  key: string;
  label: string;
}

/** A per-metric-group trend block for a single app. */
export function AppTrend({
  title,
  filters,
  metrics,
  unit,
}: {
  title: string;
  filters: Filters;
  metrics: MetricDef[];
  unit: "usd" | "number";
}) {
  const ts = useTimeseries(
    filters,
    metrics.map((m) => m.key),
    "day",
  );
  const labels = bucketLabels(ts.data);
  const fmt = (v: number) => (unit === "usd" ? formatUSD(v, { compact: true }) : formatCompact(v));
  const fmtFull = (v: number) => (unit === "usd" ? formatUSD(v) : formatNumber(v));

  const hasData = metrics.some((m) => metricValues(ts.data, m.key).some((v) => v !== 0));

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: metrics.map((m) => m.label) },
    tooltip: { trigger: "axis", valueFormatter: (v) => fmtFull(Number(v)) },
    xAxis: { type: "category", data: labels },
    yAxis: { type: "value", axisLabel: { formatter: fmt } },
    series: metrics.map((m, i) => ({
      name: m.label,
      type: "line",
      data: metricValues(ts.data, m.key),
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2, color: token(COLORS[i % COLORS.length]) },
      itemStyle: { color: token(COLORS[i % COLORS.length]) },
    })),
  };

  return (
    <ChartCard title={title}>
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && (labels.length === 0 || !hasData)}
        height={240}
      />
    </ChartCard>
  );
}

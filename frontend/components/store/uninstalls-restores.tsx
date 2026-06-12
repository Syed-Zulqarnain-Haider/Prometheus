"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useSummary, useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatNumber } from "@/lib/format";

export function UninstallsRestores({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, ["gp_uninstalls", "apple_restores"], "day");
  const summary = useSummary(filters);
  const current = summary.data?.current ?? {};
  const labels = bucketLabels(ts.data);
  const uninstalls = metricValues(ts.data, "gp_uninstalls");
  const restores = metricValues(ts.data, "apple_restores");

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: ["GP Uninstalls", "Apple Restores"] },
    tooltip: { trigger: "axis", valueFormatter: (v) => formatNumber(Number(v)) },
    xAxis: { type: "category", data: labels },
    yAxis: { type: "value" },
    series: [
      {
        name: "GP Uninstalls",
        type: "bar",
        data: uninstalls,
        itemStyle: { color: token("--color-negative") },
        barMaxWidth: 14,
      },
      {
        name: "Apple Restores",
        type: "bar",
        data: restores,
        itemStyle: { color: token("--color-purple") },
        barMaxWidth: 14,
      },
    ],
  };

  return (
    <ChartCard
      title="Uninstalls & Restores"
      action={
        <span className="text-xs text-muted-foreground">
          {formatNumber(num(current.gp_uninstalls))} uninstalls ·{" "}
          {formatNumber(num(current.apple_restores))} restores
        </span>
      }
    >
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && uninstalls.length === 0 && restores.length === 0}
        height={240}
      />
    </ChartCard>
  );
}

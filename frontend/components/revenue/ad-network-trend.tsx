"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useSummary, useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

export function AdNetworkTrend({ filters }: { filters: Filters }) {
  const ts = useTimeseries(filters, ["admob_revenue_usd", "applovin_revenue_usd"], "day");
  const summary = useSummary(filters);
  const labels = bucketLabels(ts.data);
  const admob = metricValues(ts.data, "admob_revenue_usd");
  const applovin = metricValues(ts.data, "applovin_revenue_usd");
  const current = summary.data?.current ?? {};

  const option: EChartsOption = {
    grid: { top: 28, bottom: 24, left: 8, right: 8, containLabel: true },
    legend: { top: 0, data: ["AdMob", "AppLovin"] },
    tooltip: { trigger: "axis", valueFormatter: (v) => formatUSD(Number(v), { compact: true }) },
    xAxis: { type: "category", data: labels },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series: [
      {
        name: "AdMob",
        type: "line",
        data: admob,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: token("--chart-bar") },
        itemStyle: { color: token("--chart-bar") },
      },
      {
        name: "AppLovin",
        type: "line",
        data: applovin,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: token("--chart-spark-cash") },
        itemStyle: { color: token("--chart-spark-cash") },
      },
    ],
  };

  return (
    <ChartCard
      title="Ad Revenue: AdMob vs AppLovin"
      action={
        <div className="flex gap-4 text-xs text-muted-foreground">
          <span>
            AdMob eCPM{" "}
            <span className="font-medium text-foreground">
              {formatUSD(current.admob_ecpm, { digits: 2 })}
            </span>
          </span>
          <span>
            AppLovin eCPM{" "}
            <span className="font-medium text-foreground">
              {formatUSD(current.applovin_ecpm, { digits: 2 })}
            </span>
          </span>
        </div>
      }
    >
      <Chart
        option={option}
        loading={ts.isLoading}
        error={ts.isError}
        isEmpty={!ts.isLoading && admob.length === 0 && applovin.length === 0}
        height={280}
      />
    </ChartCard>
  );
}

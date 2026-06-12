"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useSummary } from "@/lib/api-hooks";
import { num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

export function IapWaterfall({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const c = summary.data?.current ?? {};

  const gross = num(c.total_iap_gross_usd);
  const refunds = num(c.gp_iap_refunds_usd) + num(c.apple_iap_refunds_usd);
  const fees = num(c.gp_google_fee_usd) + num(c.apple_fee_usd);
  const net = num(c.total_iap_net_usd);

  const afterRefunds = gross - refunds;
  const afterFees = afterRefunds - fees;

  // Stacked-bar waterfall: invisible base + a coloured delta per step.
  const base = [0, afterRefunds, afterFees, 0];
  const reductions = [0, refunds, fees, 0];
  const totals = [gross, 0, 0, net];

  const option: EChartsOption = {
    grid: { top: 16, bottom: 24, left: 8, right: 8, containLabel: true },
    tooltip: { trigger: "item", valueFormatter: (v) => formatUSD(Number(v)) },
    xAxis: { type: "category", data: ["Gross", "Refunds", "Fees", "Net"] },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    series: [
      {
        name: "base",
        type: "bar",
        stack: "wf",
        silent: true,
        itemStyle: { color: "transparent" },
        emphasis: { disabled: true },
        data: base,
      },
      {
        name: "Reduction",
        type: "bar",
        stack: "wf",
        itemStyle: { color: token("--color-negative") },
        data: reductions,
      },
      {
        name: "Amount",
        type: "bar",
        stack: "wf",
        itemStyle: { color: token("--chart-bar") },
        data: totals,
      },
    ],
  };

  return (
    <ChartCard title="IAP Waterfall (gross → net)">
      <Chart
        option={option}
        loading={summary.isLoading}
        error={summary.isError}
        isEmpty={!summary.isLoading && gross === 0 && net === 0}
        height={280}
      />
    </ChartCard>
  );
}

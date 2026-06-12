"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useSummary } from "@/lib/api-hooks";
import { num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatNumber, formatPercent } from "@/lib/format";

export function InstallMix({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const current = summary.data?.current ?? {};
  const paid = num(current.total_paid_installs);
  const organic = num(current.store_organic_installs);
  const share = current.organic_install_share ?? (paid + organic > 0 ? organic / (paid + organic) : null);

  const option: EChartsOption = {
    tooltip: { trigger: "item", valueFormatter: (v) => formatNumber(Number(v)) },
    legend: { bottom: 0 },
    series: [
      {
        type: "pie",
        radius: ["58%", "78%"],
        center: ["50%", "44%"],
        label: { show: false },
        data: [
          { name: "Paid", value: paid, itemStyle: { color: token("--chart-bar") } },
          { name: "Organic", value: organic, itemStyle: { color: token("--chart-spark") } },
        ],
      },
    ],
  };

  return (
    <ChartCard
      title="Paid vs Organic Mix"
      action={
        <span className="text-xs text-muted-foreground">
          Organic share{" "}
          <span className="font-medium text-foreground">{formatPercent(share)}</span>
        </span>
      }
    >
      <Chart
        option={option}
        loading={summary.isLoading}
        error={summary.isError}
        isEmpty={!summary.isLoading && paid === 0 && organic === 0}
        height={240}
      />
    </ChartCard>
  );
}

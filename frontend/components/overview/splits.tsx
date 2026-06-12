"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useBreakdown } from "@/lib/api-hooks";
import { num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

const PALETTE = [
  "--chart-bar",
  "--chart-spark",
  "--chart-spark-cash",
  "--color-amber",
  "--color-orange",
  "--color-positive",
];

function BreakdownPie({
  title,
  filters,
  groupBy,
}: {
  title: string;
  filters: Filters;
  groupBy: string;
}) {
  const breakdown = useBreakdown(filters, groupBy, ["total_revenue_usd"]);
  const rows = breakdown.data?.rows ?? [];
  const data = rows.map((row, i) => ({
    name: String(row[groupBy] ?? "—"),
    value: num(row.total_revenue_usd),
    itemStyle: { color: token(PALETTE[i % PALETTE.length]) },
  }));

  const option: EChartsOption = {
    tooltip: {
      trigger: "item",
      valueFormatter: (v) => formatUSD(Number(v), { compact: true }),
    },
    legend: { type: "scroll", bottom: 0, textStyle: { fontSize: 11 } },
    series: [
      {
        type: "pie",
        radius: ["50%", "72%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        label: { show: false },
        data,
      },
    ],
  };

  return (
    <ChartCard title={title}>
      <Chart
        option={option}
        loading={breakdown.isLoading}
        error={breakdown.isError}
        isEmpty={!breakdown.isLoading && data.length === 0}
        height={240}
      />
    </ChartCard>
  );
}

export function PlatformSplit({ filters }: { filters: Filters }) {
  return <BreakdownPie title="Revenue by Platform" filters={filters} groupBy="platform" />;
}

export function PodSplit({ filters }: { filters: Filters }) {
  return <BreakdownPie title="Revenue by Pod" filters={filters} groupBy="pod" />;
}

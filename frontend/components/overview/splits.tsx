"use client";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useBreakdown } from "@/lib/api-hooks";
import { num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";
import type { Platform } from "@/lib/types";
import { useFilters } from "@/lib/use-filters";

/** Narrow the global filters into one clicked category (drill-down). Only ever NARROWS —
 * never widens — so it stays within the caller's RBAC scope. Returns null if this dimension
 * isn't a filterable one. */
function drillInto(filters: Filters, groupBy: string, value: string): Filters | null {
  if (!value) return null;
  switch (groupBy) {
    case "platform":
      return value === "ios" || value === "android"
        ? { ...filters, platform: value as Platform }
        : null;
    case "pod":
      return { ...filters, pods: [value] };
    case "publisher":
      return { ...filters, publishers: [value] };
    case "hou":
      return { ...filters, hou: [value] };
    case "app":
      return { ...filters, apps: [value] };
    default:
      return null;
  }
}

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
  const { setFilters } = useFilters();
  const breakdown = useBreakdown(filters, groupBy, ["total_revenue_usd"]);
  const rows = breakdown.data?.rows ?? [];
  const data = rows.map((row, i) => ({
    name: String(row[groupBy] ?? ""),
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
        onEvents={{
          click: (p) => {
            const next = drillInto(filters, groupBy, String(p.name));
            if (next) setFilters(next);
          },
        }}
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

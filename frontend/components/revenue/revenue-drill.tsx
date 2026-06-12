"use client";

import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { Chart, type EChartsClickParams } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useApps, useBreakdown } from "@/lib/api-hooks";
import { num, token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { formatUSD } from "@/lib/format";

const METRIC = "total_revenue_usd";
const TOP_N = 12;

export function RevenueDrill({ filters }: { filters: Filters }) {
  const [hou, setHou] = useState<string | null>(null);
  const [pod, setPod] = useState<string | null>(null);

  const level: "hou" | "pod" | "app" = hou === null ? "hou" : pod === null ? "pod" : "app";
  const groupBy = level === "app" ? "app" : level;

  // Drilling into an app list narrows server-side to the selected pod.
  const drillFilters = level === "app" && pod ? { ...filters, pods: [pod] } : filters;
  const breakdown = useBreakdown(drillFilters, groupBy, [METRIC]);

  // hou → pods mapping (from /apps) lets us restrict the pod level to the picked HoU.
  const apps = useApps();
  const houPods = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const a of apps.data?.apps ?? []) {
      if (a.hou && a.pod) {
        if (!map.has(a.hou)) map.set(a.hou, new Set());
        map.get(a.hou)?.add(a.pod);
      }
    }
    return map;
  }, [apps.data]);

  const labelKey = level === "app" ? "app_name" : level;
  let rows = [...(breakdown.data?.rows ?? [])];
  if (level === "pod" && hou && houPods.has(hou)) {
    const allowed = houPods.get(hou);
    rows = rows.filter((r) => allowed?.has(String(r.pod)));
  }
  rows.sort((a, b) => num(b[METRIC]) - num(a[METRIC]));
  rows = rows.slice(0, TOP_N);

  const labels = rows.map((r) => String(r[labelKey] ?? r[groupBy] ?? "—"));
  const values = rows.map((r) => num(r[METRIC]));

  const option: EChartsOption = {
    grid: { top: 8, bottom: 8, left: 8, right: 16, containLabel: true },
    tooltip: { trigger: "item", valueFormatter: (v) => formatUSD(Number(v)) },
    xAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatUSD(v, { compact: true }) },
    },
    yAxis: { type: "category", data: labels, inverse: true },
    series: [
      {
        type: "bar",
        data: values,
        itemStyle: { color: token("--chart-bar") },
        barMaxWidth: 22,
        cursor: level === "app" ? "default" : "pointer",
      },
    ],
  };

  const onEvents = {
    click: (params: EChartsClickParams) => {
      if (level === "hou") setHou(params.name);
      else if (level === "pod") setPod(params.name);
    },
  };

  return (
    <ChartCard
      title="Revenue Drill-down"
      action={
        <Breadcrumb
          hou={hou}
          pod={pod}
          onRoot={() => {
            setHou(null);
            setPod(null);
          }}
          onHou={() => setPod(null)}
        />
      }
    >
      <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
        {level === "app" ? "Apps (leaf)" : `Click a bar to drill into ${level === "hou" ? "pods" : "apps"}`}
      </p>
      <Chart
        option={option}
        loading={breakdown.isLoading}
        error={breakdown.isError}
        isEmpty={!breakdown.isLoading && rows.length === 0}
        height={Math.max(160, labels.length * 28 + 24)}
        onEvents={onEvents}
      />
    </ChartCard>
  );
}

function Breadcrumb({
  hou,
  pod,
  onRoot,
  onHou,
}: {
  hou: string | null;
  pod: string | null;
  onRoot: () => void;
  onHou: () => void;
}) {
  return (
    <div className="flex items-center gap-1 text-xs text-muted-foreground">
      <button type="button" className="hover:text-foreground hover:underline" onClick={onRoot}>
        All HoUs
      </button>
      {hou && (
        <>
          <ChevronRight className="h-3 w-3" />
          <button type="button" className="hover:text-foreground hover:underline" onClick={onHou}>
            {hou}
          </button>
        </>
      )}
      {pod && (
        <>
          <ChevronRight className="h-3 w-3" />
          <span className="font-medium text-foreground">{pod}</span>
        </>
      )}
    </div>
  );
}

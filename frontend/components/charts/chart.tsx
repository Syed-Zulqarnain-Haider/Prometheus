"use client";

import dynamic from "next/dynamic";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import type { EChartsOption } from "@/lib/echarts";

/** Minimal shape of an ECharts mouse-event param (e.g. a bar/segment click). */
export interface EChartsClickParams {
  name: string;
  value: unknown;
  dataIndex: number;
  seriesName?: string;
}

interface ChartProps {
  option: EChartsOption;
  loading?: boolean;
  error?: boolean;
  isEmpty?: boolean;
  height?: number;
  emptyMessage?: string;
  errorMessage?: string;
  onEvents?: Record<string, (params: EChartsClickParams) => void>;
}

// Lazy-load the ECharts renderer: the heavy charting library (echarts core +
// echarts-for-react + theme) lives entirely in chart-canvas and is code-split out
// of the initial route bundle, fetched on demand. A skeleton fills the chart's
// reserved height while the chunk loads. ssr:false — charts are client-only anyway,
// so this changes only HOW the library loads, not any chart/data behaviour.
const ChartCanvas = dynamic(
  () => import("@/components/charts/chart-canvas").then((m) => m.ChartCanvas),
  { ssr: false, loading: () => <Skeleton className="h-full w-full" /> },
);

export function Chart({
  option,
  loading = false,
  error = false,
  isEmpty = false,
  height = 320,
  emptyMessage = "No data for the selected filters",
  errorMessage = "Failed to load chart",
  onEvents,
}: ChartProps) {
  let body: ReactNode;
  if (error) {
    body = (
      <div className="flex h-full w-full items-center justify-center text-sm">
        <span className="text-[color:var(--color-negative)]">{errorMessage}</span>
      </div>
    );
  } else if (loading) {
    body = <Skeleton className="h-full w-full" />;
  } else if (isEmpty) {
    body = (
      <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    );
  } else {
    body = <ChartCanvas option={option} onEvents={onEvents} />;
  }

  return (
    <div style={{ height, width: "100%" }}>
      {body}
    </div>
  );
}

"use client";

import ReactEChartsCore from "echarts-for-react/lib/core";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { type EChartsOption, echarts } from "@/lib/echarts";
import {
  ECHARTS_THEME_NAME,
  buildEChartsTheme,
  readChartTokens,
} from "@/lib/echarts-theme";

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

/** Minimal shape of an ECharts mouse-event param (e.g. a bar/segment click). */
export interface EChartsClickParams {
  name: string;
  value: unknown;
  dataIndex: number;
  seriesName?: string;
}

function ChartFrame({
  height,
  children,
}: {
  height: number;
  children: React.ReactNode;
}) {
  return (
    <div
      className="flex w-full items-center justify-center text-sm text-muted-foreground"
      style={{ height }}
    >
      {children}
    </div>
  );
}

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
  // Register/refresh the theme whenever the dark/light mode changes.
  const { resolvedTheme } = useTheme();
  const [themeVersion, setThemeVersion] = useState(0);

  useEffect(() => {
    echarts.registerTheme(ECHARTS_THEME_NAME, buildEChartsTheme(readChartTokens()));
    setThemeVersion((v) => v + 1);
  }, [resolvedTheme]);

  if (error) {
    return (
      <ChartFrame height={height}>
        <span className="text-[color:var(--color-negative)]">{errorMessage}</span>
      </ChartFrame>
    );
  }
  if (loading) {
    return (
      <div style={{ height }}>
        <Skeleton className="h-full w-full" />
      </div>
    );
  }
  if (isEmpty) {
    return <ChartFrame height={height}>{emptyMessage}</ChartFrame>;
  }

  return (
    <ReactEChartsCore
      key={themeVersion}
      echarts={echarts}
      option={option}
      theme={ECHARTS_THEME_NAME}
      notMerge
      lazyUpdate
      style={{ height }}
      opts={{ renderer: "canvas" }}
      onEvents={onEvents}
    />
  );
}

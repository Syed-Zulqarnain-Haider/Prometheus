"use client";

import ReactEChartsCore from "echarts-for-react/lib/core";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";

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
  const { resolvedTheme } = useTheme();
  const [themeVersion, setThemeVersion] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReactEChartsCore>(null);

  // Re-register the theme whenever the dark/light mode changes.
  useEffect(() => {
    echarts.registerTheme(ECHARTS_THEME_NAME, buildEChartsTheme(readChartTokens()));
    setThemeVersion((v) => v + 1);
  }, [resolvedTheme]);

  // Keep the chart sized to its container — ECharts only auto-handles WINDOW
  // resizes, so a chart that inits inside a not-yet-laid-out grid/flex cell can
  // render blank until its container later gets a width. A ResizeObserver fixes
  // that (and dynamic layout changes) for every chart.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      chartRef.current?.getEchartsInstance()?.resize();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  let body: React.ReactNode;
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
    body = (
      <ReactEChartsCore
        ref={chartRef}
        key={themeVersion}
        echarts={echarts}
        option={option}
        theme={ECHARTS_THEME_NAME}
        notMerge
        lazyUpdate
        style={{ height: "100%", width: "100%" }}
        opts={{ renderer: "canvas" }}
        onEvents={onEvents}
      />
    );
  }

  return (
    <div ref={containerRef} style={{ height, width: "100%" }}>
      {body}
    </div>
  );
}

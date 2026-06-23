"use client";

import ReactEChartsCore from "echarts-for-react/lib/core";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";

import type { EChartsClickParams } from "@/components/charts/chart";
import { type EChartsOption, echarts } from "@/lib/echarts";
import { ECHARTS_THEME_NAME, buildEChartsTheme, readChartTokens } from "@/lib/echarts-theme";

/** The actual ECharts renderer. Split out of ``chart.tsx`` so the (heavy) charting
 *  library — ``echarts`` core, ``echarts-for-react``, and the theme — is imported
 *  ONLY here and can be code-split via ``next/dynamic`` (see chart.tsx). Behaviour is
 *  identical to the previous inline renderer: theme registration, the
 *  container-resize ResizeObserver, and the canvas options are unchanged. */
export function ChartCanvas({
  option,
  onEvents,
}: {
  option: EChartsOption;
  onEvents?: Record<string, (params: EChartsClickParams) => void>;
}) {
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
      // Guard against a disposed/stale instance: while react-grid-layout drags or
      // resizes a chart, ResizeObserver can fire after the chart is torn down.
      const instance = chartRef.current?.getEchartsInstance();
      if (instance && !instance.isDisposed()) instance.resize();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} style={{ height: "100%", width: "100%" }}>
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
    </div>
  );
}

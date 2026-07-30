"use client";

import { ChevronDown, ChevronUp, Info } from "lucide-react";
import { useTheme } from "next-themes";
import { useMemo } from "react";

import { Chart } from "@/components/charts/chart";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import { formatPercent } from "@/lib/format";

type Direction = "up" | "down" | "neutral";

/** Period-over-period direction — the SINGLE source of truth for both the % badge and the
 *  sparkline colour, so they can never disagree. Uses the EXACT guard/formula as ``Delta``:
 *  no comparison when previous is missing or zero. Colour is NEVER derived from the spark's
 *  first-vs-last point. */
function changeInfo(
  current: number | null | undefined,
  previous: number | null | undefined,
): { direction: Direction; change: number | null } {
  if (current == null || previous == null || previous === 0) {
    return { direction: "neutral", change: null };
  }
  const change = (current - previous) / Math.abs(previous);
  return { direction: change >= 0 ? "up" : "down", change };
}

/** Semantic theme token for a direction (adapts to light/dark). */
function directionToken(direction: Direction): string {
  if (direction === "up") return "--color-positive";
  if (direction === "down") return "--color-negative";
  return "--color-text-muted";
}

/** Convert a #rgb/#rrggbb token value to rgba() so we can build the gradient's fade. */
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.trim().replace("#", "");
  const read = (s: string) => parseInt(s, 16);
  if (h.length === 3) {
    return `rgba(${read(h[0] + h[0])}, ${read(h[1] + h[1])}, ${read(h[2] + h[2])}, ${alpha})`;
  }
  if (h.length === 6) {
    return `rgba(${read(h.slice(0, 2))}, ${read(h.slice(2, 4))}, ${read(h.slice(4, 6))}, ${alpha})`;
  }
  return hex; // already rgba()/named — pass through
}

/** Apple-style area sparkline: smooth line + top-down gradient fade, no axes/grid/labels,
 *  flush across the bottom. ``color`` is the directional token value resolved at render. */
function sparklineOption(values: number[], color: string): EChartsOption {
  return {
    grid: { top: 6, bottom: 0, left: 0, right: 0 },
    xAxis: { type: "category", show: false, boundaryGap: false, data: values.map((_, i) => i) },
    yAxis: { type: "value", show: false, scale: true },
    tooltip: { show: false },
    series: [
      {
        type: "line",
        data: values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.75, color },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: hexToRgba(color, 0.18) },
              { offset: 1, color: hexToRgba(color, 0) },
            ],
          },
        },
      },
    ],
  };
}

export function KpiCard({
  label,
  value,
  current,
  previous,
  spark,
  description,
  loading,
}: {
  label: string;
  value: string;
  current?: number | null;
  previous?: number | null;
  spark?: number[];
  description?: string;
  loading?: boolean;
}) {
  const { resolvedTheme } = useTheme();
  const { direction, change } = changeInfo(current, previous);

  // Resolve the directional colour from CSS tokens; recompute on theme switch so the
  // canvas-drawn sparkline follows light/dark (getComputedStyle reads the live value).
  const sparkColor = useMemo(
    () => token(directionToken(direction)) || "#888888",
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [direction, resolvedTheme],
  );

  const up = direction === "up";
  const badgeColor = `var(${directionToken(direction)})`;

  return (
    <Card className="relative flex h-full flex-col overflow-hidden">
      <div className="flex flex-col gap-1 p-4 pb-3">
        <div className="flex items-start justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {label}
          </span>
          {description && (
            <span
              title={description}
              aria-label={description}
              className="mt-0.5 shrink-0 cursor-help text-muted-foreground/70 transition-colors hover:text-muted-foreground"
            >
              <Info className="h-3.5 w-3.5" />
            </span>
          )}
        </div>

        {loading ? (
          <Skeleton className="mt-1 h-8 w-28" />
        ) : (
          <div className="mt-0.5 text-[length:var(--fs-kpi)] font-bold leading-none tracking-tight tabular-nums text-card-foreground">
            {value}
          </div>
        )}

        <div className="flex min-h-[18px] items-center">
          {!loading && direction !== "neutral" && change != null && (
            <span
              className="inline-flex items-center gap-0.5 text-xs font-semibold tabular-nums"
              style={{ color: badgeColor }}
            >
              {up ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
              {up ? "+" : "−"}
              {formatPercent(Math.abs(change), 1)}
            </span>
          )}
        </div>
      </div>

      {/* Always reserve the sparkline area so every card is the SAME height, even the
          ones without a sparkline (e.g. Profit %). */}
      <div className="mt-auto h-12 w-full">
        {spark && spark.length > 1 && (
          <Chart option={sparklineOption(spark, sparkColor)} height={48} adjustable={false} />
        )}
      </div>
    </Card>
  );
}

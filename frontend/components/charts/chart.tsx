"use client";

import dynamic from "next/dynamic";
import { type ReactNode, useMemo, useState } from "react";

import { ChartControls } from "@/components/charts/chart-controls";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type Adjustments,
  DEFAULT_ADJUSTMENTS,
  applyAdjustments,
  detectCapabilities,
} from "@/lib/chart-adjust";
import type { EChartsOption } from "@/lib/echarts";
import { cn } from "@/lib/utils";

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
  /** Generic viewer controls (type/scale/stacking/labels/transform/series switch +
   *  drag-resize). On by default; pass ``adjustable={false}`` for a chart that must
   *  stay fixed. */
  adjustable?: boolean;
}

// Lazy-load the ECharts renderer: the heavy charting library (echarts core +
// echarts-for-react + theme) lives entirely in chart-canvas and is code-split out
// of the initial route bundle, fetched on demand. A skeleton fills the chart's
// reserved height while the chunk loads. ssr:false - charts are client-only anyway,
// so this changes only HOW the library loads, not any chart/data behaviour.
const ChartCanvas = dynamic(
  () => import("@/components/charts/chart-canvas").then((m) => m.ChartCanvas),
  { ssr: false, loading: () => <Skeleton className="h-full w-full" /> },
);

// Resize bounds (px) for the drag handle - keep charts readable but flexible.
const MIN_HEIGHT = 140;
const MAX_HEIGHT = 900;

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
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
  adjustable = true,
}: ChartProps) {
  // Sparklines (under 100px) host no controls, so the house bar default would be a change
  // the viewer couldn't undo - and a 60px bar chart reads worse than a 60px line. They keep
  // the author's shape; every full-size chart gets bars.
  const [adjustments, setAdjustments] = useState<Adjustments>(() =>
    height >= 100 ? DEFAULT_ADJUSTMENTS : { ...DEFAULT_ADJUSTMENTS, type: "auto" },
  );
  const [heightOverride, setHeightOverride] = useState<number | null>(null);

  const capabilities = useMemo(() => detectCapabilities(option), [option]);
  // Only recompute the adjusted option when something that affects it changes.
  const effectiveOption = useMemo(
    () => (adjustable ? applyAdjustments(option, adjustments) : option),
    [adjustable, option, adjustments],
  );

  const effectiveHeight = heightOverride ?? height;
  // Decorative charts (e.g. KPI sparklines) are too small to host controls/resize; opt
  // them out automatically on top of any explicit ``adjustable={false}``.
  const canAdjust = adjustable && height >= 100;
  const showControls =
    canAdjust &&
    !loading &&
    !error &&
    !isEmpty &&
    (capabilities.canSwitchType ||
      capabilities.canScale ||
      capabilities.canStack ||
      capabilities.canLabel ||
      capabilities.canTransform ||
      capabilities.seriesNames.length > 0);

  const startResize = (event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation(); // don't let a parent grid (Overview drag-and-drop) start a drag
    const startY = event.clientY;
    const startH = effectiveHeight;
    const onMove = (e: PointerEvent) => {
      setHeightOverride(clamp(startH + (e.clientY - startY), MIN_HEIGHT, MAX_HEIGHT));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

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
    body = <ChartCanvas option={effectiveOption} onEvents={onEvents} />;
  }

  return (
    <div className="group relative w-full" style={{ height: effectiveHeight }}>
      <div className="absolute inset-0">{body}</div>

      {showControls && (
        <div className="pointer-events-none absolute right-1 top-1 z-10 opacity-0 transition-opacity focus-within:pointer-events-auto focus-within:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100">
          <ChartControls
            capabilities={capabilities}
            adjustments={adjustments}
            onChange={setAdjustments}
          />
        </div>
      )}

      {canAdjust && !loading && !error && !isEmpty && (
        <div
          role="separator"
          aria-orientation="horizontal"
          aria-label="Drag to resize chart"
          onPointerDown={startResize}
          className={cn(
            "absolute inset-x-0 bottom-0 z-10 flex h-3 cursor-ns-resize items-center justify-center",
            "pointer-events-none opacity-0 transition-opacity",
            "group-hover:pointer-events-auto group-hover:opacity-100",
          )}
        >
          <span className="h-1 w-8 rounded-full bg-border" />
        </div>
      )}
    </div>
  );
}

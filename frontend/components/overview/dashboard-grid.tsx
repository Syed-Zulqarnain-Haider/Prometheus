"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Responsive, WidthProvider, type Layout, type Layouts } from "react-grid-layout";

import {
  GRID_BREAKPOINT_COLS,
  GRID_BREAKPOINTS,
  GRID_MARGIN,
  GRID_ROW_HEIGHT,
  type OverviewItemId,
} from "@/lib/overview-layout";

const ResponsiveGridLayout = WidthProvider(Responsive);

/** Rows needed for `px` of content, given the grid's row height + vertical margin. */
function rowsForHeight(px: number): number {
  const [, marginY] = GRID_MARGIN;
  return Math.max(1, Math.ceil((px + marginY) / (GRID_ROW_HEIGHT + marginY)));
}

/** Measures its content's natural height and reports it (for per-widget auto-height).
 *  While editing, the widget is made non-interactive so pointer events fall through
 *  to the draggable grid item (ECharts never receives events on a moving chart). */
function MeasuredItem({
  id,
  editable,
  onMeasure,
  children,
}: {
  id: string;
  editable: boolean;
  onMeasure: (id: string, px: number) => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const report = () => onMeasure(id, el.offsetHeight);
    const observer = new ResizeObserver(report);
    observer.observe(el);
    report();
    return () => observer.disconnect();
  }, [id, onMeasure]);
  return (
    <div ref={ref} className={editable ? "pointer-events-none select-none" : undefined}>
      {children}
    </div>
  );
}

/** The Overview widget grid (drag-and-drop Phase 2).
 *
 *  Renders in BOTH view and edit mode so a saved arrangement persists outside the
 *  editor: in view mode it is static (no drag/resize) but still lays out by the saved
 *  positions; in edit mode widgets are draggable/resizable. Widgets are wrapped
 *  untouched — each keeps its own data fetching, filter reactivity, loading/empty/error
 *  states and RBAC. Per-widget auto-height (minH from a ResizeObserver) grows any cell
 *  whose content reflows taller, so saved layouts never clip. Below the `lg` breakpoint
 *  the grid is a single column (stacks vertically on tablet/mobile).
 */
export function DashboardGrid({
  items,
  layouts,
  editable,
  onLayoutsChange,
}: {
  items: Record<OverviewItemId, ReactNode>;
  layouts: Layouts;
  editable: boolean;
  onLayoutsChange: (layouts: Layouts) => void;
}) {
  const [heights, setHeights] = useState<Record<string, number>>({});

  const onMeasure = useCallback((id: string, px: number) => {
    setHeights((prev) => (Math.abs((prev[id] ?? 0) - px) > 2 ? { ...prev, [id]: px } : prev));
  }, []);

  // Inject a content-fitting minH per item so no widget is clipped. Grow-only: a
  // user can still make a cell taller than its content, never shorter than it.
  const sized = useMemo<Layouts>(() => {
    const out: Layouts = {};
    for (const bp of Object.keys(layouts) as (keyof Layouts)[]) {
      out[bp] = (layouts[bp] ?? []).map((it: Layout) => {
        const needed = heights[it.i] ? rowsForHeight(heights[it.i]) : (it.minH ?? 1);
        const minH = Math.max(it.minH ?? 1, needed);
        return { ...it, minH, h: Math.max(it.h, minH) };
      });
    }
    return out;
  }, [layouts, heights]);

  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={sized}
      breakpoints={GRID_BREAKPOINTS}
      cols={GRID_BREAKPOINT_COLS}
      rowHeight={GRID_ROW_HEIGHT}
      margin={GRID_MARGIN}
      containerPadding={[0, 0]}
      isDraggable={editable}
      isResizable={editable}
      isDroppable={false}
      compactType="vertical"
      measureBeforeMount={false}
      // Persist only real user edits; in view mode the layout is read-only.
      onLayoutChange={(_current, all) => {
        if (editable) onLayoutsChange(all);
      }}
    >
      {(Object.keys(items) as OverviewItemId[]).map((id) => (
        <div
          key={id}
          className={
            editable
              ? "h-full overflow-hidden rounded-lg ring-1 ring-primary/40 ring-offset-2 ring-offset-background"
              : "h-full overflow-hidden"
          }
          style={editable ? { cursor: "move" } : undefined}
        >
          <MeasuredItem id={id} editable={editable} onMeasure={onMeasure}>
            {items[id]}
          </MeasuredItem>
        </div>
      ))}
    </ResponsiveGridLayout>
  );
}

"use client";

import type { ReactNode } from "react";
import { Responsive, WidthProvider, type Layouts } from "react-grid-layout";

import {
  GRID_BREAKPOINT_COLS,
  GRID_BREAKPOINTS,
  GRID_MARGIN,
  GRID_ROW_HEIGHT,
  type OverviewItemId,
} from "@/lib/overview-layout";

const ResponsiveGridLayout = WidthProvider(Responsive);

/** The drag-and-drop editor grid for the Overview widgets (Phase 1).
 *
 *  Rendered only while customizing. Widgets are WRAPPED untouched — each `items[id]`
 *  is the existing widget element, which keeps its own data fetching, filter
 *  reactivity, loading/empty/error states and RBAC. The grid only positions them;
 *  it never changes the widgets or their data. No persistence yet — the layout lives
 *  in parent state and resets to default on refresh.
 *
 *  Below the `lg` breakpoint the grid is a single column (cols=1), so it stacks
 *  vertically on tablet/mobile with no dragging required.
 */
export function DashboardGrid({
  items,
  layouts,
  onLayoutsChange,
}: {
  items: Record<OverviewItemId, ReactNode>;
  layouts: Layouts;
  onLayoutsChange: (layouts: Layouts) => void;
}) {
  return (
    <ResponsiveGridLayout
      className="layout"
      layouts={layouts}
      breakpoints={GRID_BREAKPOINTS}
      cols={GRID_BREAKPOINT_COLS}
      rowHeight={GRID_ROW_HEIGHT}
      margin={GRID_MARGIN}
      containerPadding={[0, 0]}
      isDraggable
      isResizable
      isDroppable={false}
      compactType="vertical"
      measureBeforeMount={false}
      onLayoutChange={(_current, all) => onLayoutsChange(all)}
    >
      {(Object.keys(items) as OverviewItemId[]).map((id) => (
        <div
          key={id}
          className="h-full overflow-auto rounded-lg ring-1 ring-primary/40 ring-offset-2 ring-offset-background"
          style={{ cursor: "move" }}
        >
          {items[id]}
        </div>
      ))}
    </ResponsiveGridLayout>
  );
}

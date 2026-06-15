import type { Layout, Layouts } from "react-grid-layout";

/** Widget ids, in default visual order. Each maps to a wrapped Overview widget. */
export const OVERVIEW_ITEM_IDS = [
  "kpis",
  "donut-year",
  "trend",
  "donut-month",
  "publisher",
  "top-apps",
  "ratios",
  "rev-vs-spend",
  "composition",
  "platform",
  "pod",
] as const;

export type OverviewItemId = (typeof OVERVIEW_ITEM_IDS)[number];

export const GRID_COLS = 12;
export const GRID_ROW_HEIGHT = 10;
export const GRID_MARGIN: [number, number] = [16, 16];

// The default desktop arrangement:
//   row 1: KPI row (full width)
//   row 2: Yearly Progress to Target | Monthly Revenue Trend | Monthly Progress to
//          Target  (three across — the trend chart sits between the two target donuts)
//   row 3: publisher table | top-apps table
//   row 4: ROAS/CPI ratio cards (full width)
//   row 5: revenue-vs-spend | revenue composition
//   row 6: platform donut | pod donut
// Heights (h × rowHeight + margins) are tuned to each widget's natural height. The
// top row is thirds (w4); the donuts' ring + 3-row panel stacks within the narrower
// cell (container-responsive), so nothing clips. Below lg the grid stacks vertically.
const LG_LAYOUT: Layout[] = [
  { i: "kpis", x: 0, y: 0, w: 12, h: 5, minW: 6, minH: 4 },
  { i: "donut-year", x: 0, y: 5, w: 4, h: 16, minW: 3, minH: 9 },
  { i: "trend", x: 4, y: 5, w: 4, h: 16, minW: 3, minH: 9 },
  { i: "donut-month", x: 8, y: 5, w: 4, h: 16, minW: 3, minH: 9 },
  { i: "publisher", x: 0, y: 21, w: 6, h: 16, minW: 3, minH: 9 },
  { i: "top-apps", x: 6, y: 21, w: 6, h: 16, minW: 3, minH: 9 },
  { i: "ratios", x: 0, y: 37, w: 12, h: 5, minW: 6, minH: 4 },
  { i: "rev-vs-spend", x: 0, y: 42, w: 6, h: 14, minW: 3, minH: 9 },
  { i: "composition", x: 6, y: 42, w: 6, h: 14, minW: 3, minH: 9 },
  { i: "platform", x: 0, y: 56, w: 6, h: 13, minW: 3, minH: 9 },
  { i: "pod", x: 6, y: 56, w: 6, h: 13, minW: 3, minH: 9 },
];

/** A single-column stack (mobile/tablet) preserving the default order. */
function stacked(items: Layout[]): Layout[] {
  let y = 0;
  return items.map((it) => {
    const placed: Layout = { ...it, x: 0, y, w: 1 };
    y += it.h;
    return placed;
  });
}

/** Build a fresh copy of the default layouts (so callers never mutate the source). */
export function defaultLayouts(): Layouts {
  const lg = LG_LAYOUT.map((l) => ({ ...l }));
  const stack = stacked(LG_LAYOUT);
  return { lg, md: stack, sm: stack, xs: stack, xxs: stack };
}

// Below the `lg` breakpoint the grid is a single column (matches the original
// `lg:grid-cols-*` behaviour — stacked on tablet/mobile, no dragging needed).
export const GRID_BREAKPOINTS = { lg: 1024, md: 768, sm: 640, xs: 480, xxs: 0 };
export const GRID_BREAKPOINT_COLS = { lg: GRID_COLS, md: 1, sm: 1, xs: 1, xxs: 1 };

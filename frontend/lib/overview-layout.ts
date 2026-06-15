import type { Layout, Layouts } from "react-grid-layout";

/** Widget ids, in default visual order. Each maps to a wrapped Overview widget. */
export const OVERVIEW_ITEM_IDS = [
  "kpis",
  "revenue-target",
  "revenue-target-month",
  "donut-year",
  "trend",
  "donut-month",
  "ratios",
  "rev-vs-spend",
  "composition",
  "platform",
  "pod",
  "publisher",
  "top-apps",
] as const;

export type OverviewItemId = (typeof OVERVIEW_ITEM_IDS)[number];

export const GRID_COLS = 12;
export const GRID_ROW_HEIGHT = 10;
export const GRID_MARGIN: [number, number] = [16, 16];

// The default desktop arrangement:
//   row 1: KPI row (full width)
//   row 2: yearly progress ring (full width)
//   row 3: monthly progress ring (full width)
//   row 4: yearly progress donut | monthly progress donut  (ring + 3 rows each)
//   row 5: monthly trend (full width)
//   row 6: ROAS/CPI ratio cards (full width)
//   row 7: revenue-vs-spend | revenue composition
//   row 8: platform donut | pod donut
//   row 9: publisher table | top-apps table
// Heights (h × rowHeight + margins) are tuned to each widget's natural height. The
// progress donuts are half-width (w6) so their ring + 3-row panel fits side by side.
const LG_LAYOUT: Layout[] = [
  { i: "kpis", x: 0, y: 0, w: 12, h: 5, minW: 6, minH: 4 },
  { i: "revenue-target", x: 0, y: 5, w: 12, h: 10, minW: 4, minH: 8 },
  { i: "revenue-target-month", x: 0, y: 15, w: 12, h: 10, minW: 4, minH: 8 },
  { i: "donut-year", x: 0, y: 25, w: 6, h: 11, minW: 4, minH: 8 },
  { i: "donut-month", x: 6, y: 25, w: 6, h: 11, minW: 4, minH: 8 },
  { i: "trend", x: 0, y: 36, w: 12, h: 13, minW: 3, minH: 9 },
  { i: "ratios", x: 0, y: 49, w: 12, h: 5, minW: 6, minH: 4 },
  { i: "rev-vs-spend", x: 0, y: 54, w: 6, h: 14, minW: 3, minH: 9 },
  { i: "composition", x: 6, y: 54, w: 6, h: 14, minW: 3, minH: 9 },
  { i: "platform", x: 0, y: 68, w: 6, h: 13, minW: 3, minH: 9 },
  { i: "pod", x: 6, y: 68, w: 6, h: 13, minW: 3, minH: 9 },
  { i: "publisher", x: 0, y: 81, w: 6, h: 16, minW: 3, minH: 9 },
  { i: "top-apps", x: 6, y: 81, w: 6, h: 16, minW: 3, minH: 9 },
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

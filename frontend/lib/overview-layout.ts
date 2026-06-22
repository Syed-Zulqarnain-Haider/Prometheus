import type { Layout, Layouts } from "react-grid-layout";

/** Draggable widget ids, in default visual order. The KPI row is NOT here — it is a
 *  fixed full-width header rendered above the grid (never draggable, never clipped). */
export const OVERVIEW_ITEM_IDS = [
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

// The default desktop arrangement for the DRAGGABLE area (everything below the fixed
// KPI header):
//   row 1: Yearly Progress to Target | Monthly Revenue Trend | Monthly Progress to
//          Target  (three across — the trend chart sits between the two target donuts)
//   row 2: Publisher Performance table (full width, ~10 columns)
//   row 3: Top Apps by Revenue table (full width, ~10 columns)
//   row 4: ROAS/CPI ratio cards (full width)
//   row 5: revenue-vs-spend | revenue composition
//   row 6: platform donut | pod donut
// Heights (h × rowHeight + margins) are tuned to each widget's natural height; the
// runtime auto-height (per-widget minH from a ResizeObserver) grows any cell whose
// content reflows taller so saved arrangements never clip. Below lg the grid stacks.
const LG_LAYOUT: Layout[] = [
  { i: "donut-year", x: 0, y: 0, w: 4, h: 16, minW: 3, minH: 9 },
  { i: "trend", x: 4, y: 0, w: 4, h: 16, minW: 3, minH: 9 },
  { i: "donut-month", x: 8, y: 0, w: 4, h: 16, minW: 3, minH: 9 },
  { i: "publisher", x: 0, y: 16, w: 12, h: 18, minW: 4, minH: 10 },
  { i: "top-apps", x: 0, y: 34, w: 12, h: 18, minW: 4, minH: 10 },
  { i: "ratios", x: 0, y: 52, w: 12, h: 5, minW: 6, minH: 4 },
  { i: "rev-vs-spend", x: 0, y: 57, w: 6, h: 14, minW: 3, minH: 9 },
  { i: "composition", x: 6, y: 57, w: 6, h: 14, minW: 3, minH: 9 },
  { i: "platform", x: 0, y: 71, w: 6, h: 13, minW: 3, minH: 9 },
  { i: "pod", x: 6, y: 71, w: 6, h: 13, minW: 3, minH: 9 },
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

/** Reconcile a saved layout with the current widget set:
 *  - keep the saved position for every widget that still exists,
 *  - fill in any NEW widget (added since the layout was saved) from the default,
 *  - drop any stale id (e.g. a removed widget) so it can never break the grid.
 *  This makes restored layouts robust to widget changes between releases. */
export function normalizeLayouts(saved: Layouts): Layouts {
  const def = defaultLayouts();
  const known = new Set<string>(OVERVIEW_ITEM_IDS);
  const out: Layouts = {};
  for (const bp of Object.keys(def) as (keyof Layouts)[]) {
    const defItems = def[bp] ?? [];
    const savedById = new Map(
      (saved[bp] ?? []).filter((i) => known.has(i.i)).map((i) => [i.i, i]),
    );
    out[bp] = defItems.map((d) => {
      const s = savedById.get(d.i);
      // Keep saved x/y/w/h, but always re-apply the current min constraints.
      return s ? { ...s, minW: d.minW, minH: d.minH } : d;
    });
  }
  return out;
}

// Below the `lg` breakpoint the grid is a single column (matches the original
// `lg:grid-cols-*` behaviour — stacked on tablet/mobile, no dragging needed).
export const GRID_BREAKPOINTS = { lg: 1024, md: 768, sm: 640, xs: 480, xxs: 0 };
export const GRID_BREAKPOINT_COLS = { lg: GRID_COLS, md: 1, sm: 1, xs: 1, xxs: 1 };

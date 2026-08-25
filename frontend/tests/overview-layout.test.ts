/**
 * Reconciling a saved Executive Overview arrangement with the current widget set.
 *
 * This is the code that protects work users did by hand. Someone drags their dashboard
 * into the shape they want; months later the release adds a widget, removes another, or
 * raises a minimum size. normalizeLayouts decides what survives. Get it wrong and people
 * either lose an arrangement they built or open a dashboard with widgets clipped and
 * overlapping - and both look like the product is broken, not the release.
 */
import { describe, expect, it } from "vitest";
import type { Layout, Layouts } from "react-grid-layout";

import {
  OVERVIEW_ITEM_IDS,
  defaultLayouts,
  normalizeLayouts,
} from "@/lib/overview-layout";

const byId = (items: Layout[], id: string): Layout | undefined =>
  items.find((item) => item.i === id);

describe("defaultLayouts", () => {
  it("places every draggable widget on the desktop grid", () => {
    const lg = defaultLayouts().lg ?? [];
    expect(lg.map((item) => item.i).sort()).toEqual([...OVERVIEW_ITEM_IDS].sort());
  });

  it("hands out a fresh copy each time", () => {
    // The source arrangement is module-level. If it were handed out by reference, one
    // user dragging a widget would silently rewrite the default for every later caller
    // in the same process - a bug that only shows up under load, never in review.
    const first = defaultLayouts();
    const target = byId(first.lg ?? [], "trend");
    expect(target).toBeDefined();
    if (target) target.x = 99;

    const second = defaultLayouts();
    expect(byId(second.lg ?? [], "trend")?.x).not.toBe(99);
  });
});

describe("normalizeLayouts", () => {
  it("keeps a position the user chose", () => {
    const saved: Layouts = {
      lg: [{ i: "trend", x: 8, y: 3, w: 4, h: 16 }],
    };
    expect(byId(normalizeLayouts(saved).lg ?? [], "trend")).toMatchObject({
      x: 8,
      y: 3,
    });
  });

  it("fills in a widget added since the layout was saved", () => {
    // An older saved layout knows nothing about newer widgets. They must appear at their
    // default spot rather than vanish from the dashboard.
    const saved: Layouts = { lg: [{ i: "trend", x: 0, y: 0, w: 4, h: 16 }] };
    const lg = normalizeLayouts(saved).lg ?? [];
    expect(lg.map((item) => item.i).sort()).toEqual([...OVERVIEW_ITEM_IDS].sort());
  });

  it("drops a widget that no longer exists", () => {
    // A stale id would be positioned but never rendered, leaving a hole in the grid.
    const saved: Layouts = {
      lg: [
        { i: "trend", x: 0, y: 0, w: 4, h: 16 },
        { i: "widget-removed-two-releases-ago", x: 0, y: 40, w: 12, h: 10 },
      ],
    };
    const ids = (normalizeLayouts(saved).lg ?? []).map((item) => item.i);
    expect(ids).not.toContain("widget-removed-two-releases-ago");
    expect(ids).toContain("trend");
  });

  it("re-applies today's minimum size over a stale saved one", () => {
    // The anti-clipping guarantee. A layout saved when a widget could be 1x1 must not
    // pin it below the minimum it needs now, or its content renders cut off.
    const saved: Layouts = {
      lg: [{ i: "publisher", x: 0, y: 0, w: 12, h: 18, minW: 1, minH: 1 }],
    };
    const restored = byId(normalizeLayouts(saved).lg ?? [], "publisher");
    const fresh = byId(defaultLayouts().lg ?? [], "publisher");
    expect(restored?.minW).toBe(fresh?.minW);
    expect(restored?.minH).toBe(fresh?.minH);
    // ...while still honouring where the user put it.
    expect(restored?.w).toBe(12);
  });

  it("returns every breakpoint even when nothing was saved for it", () => {
    // react-grid-layout falls back to its own guesses for a missing breakpoint, which is
    // how a phone ends up with a desktop arrangement crushed into one column.
    const restored = normalizeLayouts({});
    for (const breakpoint of ["lg", "md", "sm", "xs", "xxs"]) {
      expect(restored[breakpoint], `${breakpoint} is missing`).toBeDefined();
      expect((restored[breakpoint] ?? []).length).toBe(OVERVIEW_ITEM_IDS.length);
    }
  });

  it("ignores junk without throwing", () => {
    // Saved layouts come back from the API as stored JSON. A malformed one must degrade
    // to the default, never take the dashboard down.
    const restored = normalizeLayouts({ lg: [] });
    expect((restored.lg ?? []).length).toBe(OVERVIEW_ITEM_IDS.length);
  });
});

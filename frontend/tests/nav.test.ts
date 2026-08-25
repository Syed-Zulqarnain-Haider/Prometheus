/**
 * Invariants of the sidebar navigation.
 *
 * nav.ts broke three times in one week, each time differently: an entry lost its href to a
 * line-based edit, a merge left a duplicate route, and an icon import was stripped because
 * `type LucideIcon` was mistaken for a value import. All three shipped past review and were
 * caught by the production build or not at all. These are the invariants each of them
 * violated, pinned so the next one fails here instead.
 *
 * Nothing here asserts the exact set of pages - that changes as the product does. It
 * asserts the properties every entry must hold no matter what the set becomes.
 */
import { describe, expect, it } from "vitest";

import { NAV_ITEMS } from "@/lib/nav";

// Routes that must never be advertised to a caller without the admin_panel capability.
// Frontend hiding is cosmetic - the server is the real gate - but an entry that quietly
// loses requiresAdmin still tells every viewer these pages exist.
const ADMIN_ONLY = ["/admin", "/data-health"];

describe("sidebar navigation", () => {
  it("has entries at all", () => {
    // Guards the rest of this file: every assertion below passes vacuously on an empty
    // array, which is exactly what a botched edit to nav.ts could leave behind.
    expect(NAV_ITEMS.length).toBeGreaterThanOrEqual(8);
  });

  it("gives every entry a usable href, label and icon", () => {
    for (const item of NAV_ITEMS) {
      expect(item.href, `entry ${item.label} has no href`).toBeTruthy();
      expect(item.href.startsWith("/"), `${item.href} is not an absolute path`).toBe(true);
      expect(item.label?.trim(), `entry ${item.href} has no label`).toBeTruthy();
      // An undefined icon is a stripped import: renders as a crash, not a missing glyph.
      expect(item.icon, `entry ${item.href} has no icon`).toBeDefined();
    }
  });

  it("points each route at exactly one entry", () => {
    // A duplicate href means two items claim the active state and one is unreachable -
    // the shape a bad merge of two pages leaves behind.
    const hrefs = NAV_ITEMS.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("does not label two entries the same", () => {
    const labels = NAV_ITEMS.map((i) => i.label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("keeps the admin routes behind requiresAdmin", () => {
    for (const href of ADMIN_ONLY) {
      const item = NAV_ITEMS.find((i) => i.href === href);
      expect(item, `${href} has vanished from the nav`).toBeDefined();
      expect(item?.requiresAdmin, `${href} is no longer admin-gated`).toBe(true);
    }
  });

  it("gates a deliberate, reviewable set and nothing by accident", () => {
    // The reverse mistake: marking an ordinary page admin-only hides it from the people
    // who need it, and nobody reports a page they never knew existed. This cannot be
    // inferred from the URL - /pod-owners is admin-only and lives nowhere near /admin -
    // so the list is explicit. Gating a new page is a decision, and adding it here is
    // how that decision gets seen by a reviewer rather than slipping through.
    const INTENTIONALLY_GATED = [...ADMIN_ONLY, "/pod-owners", "/security"];
    for (const item of NAV_ITEMS.filter((i) => i.requiresAdmin)) {
      expect(
        INTENTIONALLY_GATED.includes(item.href) || item.href.startsWith("/admin"),
        `${item.href} is admin-gated but is not in the reviewed list in this test - ` +
          "if that is intentional, add it",
      ).toBe(true);
    }
  });
});

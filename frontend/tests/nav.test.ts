import { describe, expect, it } from "vitest";

import { NAV_ITEMS } from "@/lib/nav";

/** The sidebar hides admin-only routes from non-admins. This is COSMETIC (the server still
 * enforces RBAC), but the gating logic must be correct so non-admins never see admin links. */
function visibleTo(isAdmin: boolean) {
  return NAV_ITEMS.filter((n) => !n.requiresAdmin || isAdmin).map((n) => n.href);
}

describe("nav RBAC gating", () => {
  it("hides admin-only routes from non-admins", () => {
    const nonAdmin = visibleTo(false);
    expect(nonAdmin).not.toContain("/admin");
    expect(nonAdmin).not.toContain("/app-master");
    expect(nonAdmin).not.toContain("/data-health");
    // …but keeps the analytics pages everyone gets.
    expect(nonAdmin).toContain("/overview");
    expect(nonAdmin).toContain("/reports");
  });

  it("shows every route to admins", () => {
    const admin = visibleTo(true);
    expect(admin).toContain("/admin");
    expect(admin).toContain("/app-master");
    expect(admin).toEqual(NAV_ITEMS.map((n) => n.href));
  });
});

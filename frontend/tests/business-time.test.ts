import { describe, expect, it } from "vitest";

import { BUSINESS_TIME_ZONE, businessToday } from "@/lib/business-time";

// The business clock is what stops one viewer's machine timezone from showing them a
// different "today" than the next desk - the timezone class of bug the audit reported.
describe("business-time", () => {
  it("is pinned to the business timezone, not the viewer's", () => {
    expect(BUSINESS_TIME_ZONE).toBe("Asia/Karachi");
  });
  it("returns local midnight so date-fns reads clean calendar fields", () => {
    const d = businessToday();
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
    expect(d.getSeconds()).toBe(0);
  });
  it("returns a valid date", () => {
    expect(Number.isNaN(businessToday().getTime())).toBe(false);
  });
});

import { describe, expect, it } from "vitest";

import {
  defaultFilters,
  filtersToApiQuery,
  filtersToParams,
  parseFilters,
  presetRange,
} from "@/lib/filters";

describe("filters", () => {
  it("defaults to the 30D preset with an inclusive 30-day window", () => {
    const f = defaultFilters();
    expect(f.preset).toBe("30D");
    const { from, to } = presetRange("30D");
    expect(f.dateFrom).toBe(from);
    expect(f.dateTo).toBe(to);
    // 30D is today minus 29 days .. today (inclusive) → 30 calendar days apart is 29.
    const days = (new Date(to).getTime() - new Date(from).getTime()) / 86_400_000;
    expect(Math.round(days)).toBe(29);
  });

  it("round-trips through URL params without losing selections", () => {
    const f = defaultFilters();
    f.platform = "ios";
    f.compare = true;
    f.podOwners = ["PO1", "PO2"];
    f.apps = ["appA"];
    const back = parseFilters(filtersToParams(f));
    expect(back.platform).toBe("ios");
    expect(back.compare).toBe(true);
    expect(back.podOwners).toEqual(["PO1", "PO2"]);
    expect(back.apps).toEqual(["appA"]);
  });

  it("ignores an invalid platform param (never widens beyond ios/android)", () => {
    const params = new URLSearchParams({ platform: "windows" });
    expect(parseFilters(params).platform).toBeNull();
  });

  it("maps to snake_case API query keys and omits an unset platform", () => {
    const f = defaultFilters();
    f.podOwners = ["PO1"];
    const q = filtersToApiQuery(f);
    expect(q).not.toHaveProperty("platform"); // null platform is omitted, never sent
    expect(q.pod_owners).toEqual(["PO1"]);
    expect(q.date_from).toBe(f.dateFrom);
    expect(q.compare).toBe(false);
  });
});

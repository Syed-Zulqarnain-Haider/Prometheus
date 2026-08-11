import {
  activeFilterCount,
  defaultFilters,
  filtersToParams,
  isFiltered,
  parseFilters,
  presetRange,
} from "@/lib/filters";

describe("activeFilterCount / isFiltered - drives the Clear filters button", () => {
  it("counts nothing on a fresh set of filters", () => {
    expect(activeFilterCount(defaultFilters())).toBe(0);
    expect(isFiltered(defaultFilters())).toBe(false);
  });

  it("counts each populated dimension once, however many values it holds", () => {
    const f = { ...defaultFilters(), apps: ["a", "b", "c"] };
    expect(activeFilterCount(f)).toBe(1);
    expect(isFiltered(f)).toBe(true);
  });

  it("adds up across dimensions, platform and compare", () => {
    const f = {
      ...defaultFilters(),
      apps: ["a"],
      consoles: ["ios"],
      podOwners: ["PO1"],
      platform: "ios" as const,
      compare: true,
    };
    expect(activeFilterCount(f)).toBe(5);
  });

  it("counts a non-default date range as exactly one filter", () => {
    const seven = presetRange("7D");
    const f = { ...defaultFilters(), preset: "7D" as const, dateFrom: seven.from, dateTo: seven.to };
    expect(activeFilterCount(f)).toBe(1);
  });

  it("counts every list dimension - none is silently skipped", () => {
    // Guards the LIST_FILTER_KEYS loop: a dimension added to Filters but left out of the
    // constant would make Clear under-report, which is how a filter goes invisible.
    const base = defaultFilters();
    const lists = [
      "pods",
      "publishers",
      "apps",
      "hou",
      "podOwners",
      "consoles",
      "developers",
      "googlePlayAccounts",
      "appleAccounts",
      "packages",
      "bundles",
    ] as const;
    for (const key of lists) {
      expect(activeFilterCount({ ...base, [key]: ["x"] })).toBe(1);
    }
  });

  it("clearing to defaults returns the count to zero", () => {
    const dirty = { ...defaultFilters(), apps: ["a"], compare: true, platform: "android" as const };
    expect(activeFilterCount(dirty)).toBeGreaterThan(0);
    expect(activeFilterCount(defaultFilters())).toBe(0);
  });
});

describe("parseFilters - named presets are recomputed, not read back", () => {
  it("ignores stale from/to carried by a bookmark on a named preset", () => {
    const params = new URLSearchParams({
      preset: "today",
      from: "2020-01-01",
      to: "2020-01-01",
    });
    const parsed = parseFilters(params);
    const today = presetRange("today");
    expect(parsed.preset).toBe("today");
    expect(parsed.dateFrom).toBe(today.from);
    expect(parsed.dateTo).toBe(today.to);
  });

  it("honours stored dates only for preset=custom", () => {
    const params = new URLSearchParams({
      preset: "custom",
      from: "2026-07-01",
      to: "2026-07-31",
    });
    const parsed = parseFilters(params);
    expect(parsed.dateFrom).toBe("2026-07-01");
    expect(parsed.dateTo).toBe("2026-07-31");
  });

  it("falls back to the default preset for an unknown one", () => {
    const parsed = parseFilters(new URLSearchParams({ preset: "nonsense" }));
    expect(parsed.preset).toBe(defaultFilters().preset);
  });

  it("round-trips a custom range through the URL", () => {
    const f = {
      ...defaultFilters(),
      preset: "custom" as const,
      dateFrom: "2026-07-01",
      dateTo: "2026-07-31",
      apps: ["a", "b"],
      consoles: ["ios"],
    };
    const back = parseFilters(filtersToParams(f));
    expect(back.dateFrom).toBe(f.dateFrom);
    expect(back.dateTo).toBe(f.dateTo);
    expect(back.apps).toEqual(f.apps);
    expect(back.consoles).toEqual(f.consoles);
  });
});

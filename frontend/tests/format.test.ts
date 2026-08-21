import { describe, expect, it } from "vitest";

import {
  formatCompact,
  formatDateTime,
  formatMultiplier,
  formatNumber,
  formatPercent,
  formatUSD,
} from "@/lib/format";

// Money and metric formatting sit under every KPI, table cell and export in a financial
// dashboard. A silent regression here misreports revenue, so the contract is pinned.
describe("formatUSD", () => {
  it("renders whole-dollar currency with grouping", () => {
    expect(formatUSD(1234850)).toBe("$1,234,850");
  });
  it("compacts large values", () => {
    expect(formatUSD(1230000, { compact: true })).toBe("$1.23M");
  });
  it("returns a dash for null/undefined/NaN, never $0 or NaN", () => {
    expect(formatUSD(null)).toBe("-");
    expect(formatUSD(undefined)).toBe("-");
    expect(formatUSD(Number.NaN)).toBe("-");
  });
  it("keeps a real zero distinct from missing", () => {
    expect(formatUSD(0)).toBe("$0");
  });
  it("renders negatives (refunds/adjustments), not absolutes", () => {
    expect(formatUSD(-500)).toBe("-$500");
  });
});

describe("formatPercent", () => {
  it("scales a fraction to a percentage with one decimal", () => {
    expect(formatPercent(0.704)).toBe("70.4%");
  });
  it("is a dash for null, never 0.0% (a real zero would be 0)", () => {
    expect(formatPercent(null)).toBe("-");
    expect(formatPercent(0)).toBe("0.0%");
  });
});

describe("formatMultiplier / formatCompact / formatNumber", () => {
  it("suffixes ROAS with the multiplier glyph", () => {
    expect(formatMultiplier(2.45)).toBe("2.45×");
  });
  it("groups integers", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
  });
  it("compacts counts", () => {
    expect(formatCompact(3400)).toBe("3.4K");
  });
  it("all guard nil to a dash", () => {
    expect(formatMultiplier(null)).toBe("-");
    expect(formatNumber(undefined)).toBe("-");
    expect(formatCompact(Number.NaN)).toBe("-");
  });
});

describe("formatDateTime", () => {
  it("is a dash for empty or unparseable input, never 'Invalid Date'", () => {
    expect(formatDateTime(null)).toBe("-");
    expect(formatDateTime("")).toBe("-");
    expect(formatDateTime("not-a-date")).toBe("-");
  });
});

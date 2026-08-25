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
//
// What a MISSING value renders as is a product choice - this build shows an empty cell,
// another might show a dash - so these tests pin the property rather than the glyph. The
// property is the part that must never move: a missing value is never dressed up as a
// real one. Apple's feed lags two to three days, so nulls in recent rows are routine, and
// printing them as $0 reports a revenue cliff that did not happen.
const PLACEHOLDERS = ["-", "\u2014", ""];

function expectMissing(rendered: string, label: string): void {
  expect(
    PLACEHOLDERS,
    `${label} rendered ${JSON.stringify(rendered)} for a missing value`,
  ).toContain(rendered);
}

describe("formatUSD", () => {
  it("renders whole-dollar currency with grouping", () => {
    expect(formatUSD(1234850)).toBe("$1,234,850");
  });
  it("compacts large values", () => {
    expect(formatUSD(1230000, { compact: true })).toBe("$1.23M");
  });
  it("never renders a missing amount as $0 or NaN", () => {
    expectMissing(formatUSD(null), "formatUSD(null)");
    expectMissing(formatUSD(undefined), "formatUSD(undefined)");
    expectMissing(formatUSD(Number.NaN), "formatUSD(NaN)");
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
  it("never renders a missing share as 0.0% (a real zero still does)", () => {
    expectMissing(formatPercent(null), "formatPercent(null)");
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
  it("all guard a missing value", () => {
    expectMissing(formatMultiplier(null), "formatMultiplier(null)");
    expectMissing(formatNumber(undefined), "formatNumber(undefined)");
    expectMissing(formatCompact(Number.NaN), "formatCompact(NaN)");
  });
});

describe("formatDateTime", () => {
  it("never renders 'Invalid Date' for empty or unparseable input", () => {
    for (const input of [null, "", "not-a-date"]) {
      const rendered = formatDateTime(input);
      expect(rendered).not.toContain("Invalid");
      expectMissing(rendered, `formatDateTime(${JSON.stringify(input)})`);
    }
  });

  it("uses the same placeholder as every other formatter", () => {
    // A dashboard that shows "-" in one column and a blank in the next reads as a
    // rendering bug. Whichever glyph is chosen, it has to be chosen once.
    const shown = new Set([
      formatUSD(null),
      formatPercent(null),
      formatNumber(null),
      formatCompact(null),
      formatMultiplier(null),
      formatDateTime(null),
    ]);
    expect(
      shown.size,
      `formatters disagree: ${[...shown].map((s) => JSON.stringify(s)).join(", ")}`,
    ).toBe(1);
  });
});

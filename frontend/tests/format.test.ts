import { describe, expect, it } from "vitest";

import {
  escapeHtml,
  formatCompact,
  formatMultiplier,
  formatNumber,
  formatPercent,
  formatUSD,
} from "@/lib/format";

describe("format helpers", () => {
  it("formats USD, compact and standard", () => {
    expect(formatUSD(1234567)).toBe("$1,234,567");
    expect(formatUSD(1234567, { compact: true })).toBe("$1.23M");
  });

  it("returns empty string for nil / NaN (never '$NaN')", () => {
    expect(formatUSD(null)).toBe("");
    expect(formatUSD(undefined)).toBe("");
    expect(formatUSD(Number.NaN)).toBe("");
    expect(formatNumber(null)).toBe("");
    expect(formatPercent(null)).toBe("");
    expect(formatMultiplier(null)).toBe("");
  });

  it("formats fractions as percentages", () => {
    expect(formatPercent(0.704)).toBe("70.4%");
    expect(formatPercent(0.704, 0)).toBe("70%");
  });

  it("formats multipliers (ROAS)", () => {
    expect(formatMultiplier(2.454)).toBe("2.45×");
  });

  it("formats grouped integers and compact numbers", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
    expect(formatCompact(1200)).toBe("1.2K");
  });
});

describe("escapeHtml (XSS guard for chart tooltips)", () => {
  it("neutralizes an app name carrying an HTML payload", () => {
    const evil = 'App <img src=x onerror="alert(1)">';
    const escaped = escapeHtml(evil);
    expect(escaped).not.toContain("<img");
    expect(escaped).toContain("&lt;img");
    expect(escaped).toContain("&quot;");
  });

  it("escapes all five sensitive characters", () => {
    expect(escapeHtml(`&<>"'`)).toBe("&amp;&lt;&gt;&quot;&#39;");
  });
});

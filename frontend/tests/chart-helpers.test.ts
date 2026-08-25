/**
 * Coercion of API metric values into chart input.
 *
 * MetricValue is `number | string | null` because the serving layer returns numerics as
 * strings and absent metrics as null. Every chart on the platform funnels through num(),
 * so what it does with a null decides whether a gap in the data reads as a real zero -
 * which matters here more than usual: Apple's feed lags two to three days, so recent
 * rows legitimately carry nulls that must not be drawn as a revenue cliff.
 */
import { describe, expect, it } from "vitest";

import { bucketLabels, metricValues, num, token } from "@/lib/chart-helpers";
import type { TimeseriesResponse } from "@/lib/types";

const series = (rows: Record<string, string | number | null>[]) =>
  ({ series: rows } as unknown as TimeseriesResponse);

describe("num", () => {
  it("passes numbers through", () => {
    expect(num(42)).toBe(42);
    expect(num(-3.5)).toBe(-3.5);
    expect(num(0)).toBe(0);
  });

  it("parses the numeric strings the API sends", () => {
    // Postgres NUMERIC arrives as a string over JSON; charting it as NaN would blank the
    // series without any error anywhere.
    expect(num("1234.56")).toBe(1234.56);
    expect(num("-7")).toBe(-7);
  });

  it("treats a missing metric as zero rather than NaN", () => {
    expect(num(null)).toBe(0);
    expect(num(undefined)).toBe(0);
  });

  it("never returns NaN or Infinity", () => {
    // A single NaN in a series silently collapses an ECharts axis; this is the guard.
    for (const junk of ["", "  ", "abc", "12abc", "1/0"]) {
      const result = num(junk as never);
      expect(Number.isFinite(result), `num(${JSON.stringify(junk)}) is not finite`).toBe(true);
    }
  });
});

describe("bucketLabels", () => {
  it("trims a timestamp to its date", () => {
    expect(bucketLabels(series([{ bucket: "2026-08-25T00:00:00Z" }]))).toEqual(["2026-08-25"]);
  });

  it("survives an absent response", () => {
    // Every chart renders before its query resolves; undefined must be an empty axis.
    expect(bucketLabels(undefined)).toEqual([]);
  });
});

describe("metricValues", () => {
  it("pulls one metric out of the series in order", () => {
    const ts = series([
      { bucket: "2026-08-23", total_revenue_usd: "10" },
      { bucket: "2026-08-24", total_revenue_usd: 20 },
    ]);
    expect(metricValues(ts, "total_revenue_usd")).toEqual([10, 20]);
  });

  it("zero-fills a metric the caller is not permitted to see", () => {
    // Forbidden columns are never serialized, so the key is simply absent. The chart must
    // draw an empty series, not crash on undefined.
    const ts = series([{ bucket: "2026-08-24", total_revenue_usd: 5 }]);
    expect(metricValues(ts, "total_iap_net_usd")).toEqual([0]);
  });

  it("survives an absent response", () => {
    expect(metricValues(undefined, "total_revenue_usd")).toEqual([]);
  });
});

describe("token", () => {
  it("returns empty on the server instead of touching document", () => {
    // Called during SSR this would otherwise throw on `document`, taking out the whole
    // page rather than one chart colour.
    expect(token("--color-accent")).toBe("");
  });
});

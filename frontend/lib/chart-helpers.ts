import type { MetricValue, TimeseriesResponse } from "@/lib/types";

/** Read a CSS token at runtime (client-side). */
export function token(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function num(value: MetricValue | undefined): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export function bucketLabels(ts: TimeseriesResponse | undefined): string[] {
  return (ts?.series ?? []).map((row) => String(row.bucket).slice(0, 10));
}

export function metricValues(
  ts: TimeseriesResponse | undefined,
  metric: string,
): number[] {
  return (ts?.series ?? []).map((row) => num(row[metric]));
}

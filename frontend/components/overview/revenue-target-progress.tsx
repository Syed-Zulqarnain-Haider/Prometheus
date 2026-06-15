"use client";

import { format, startOfYear } from "date-fns";
import { useMemo } from "react";

import { Chart } from "@/components/charts/chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSummary } from "@/lib/api-hooks";
import { token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import { defaultFilters, type Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

// Config defaults. `target` is a fixed strategic goal and `targetDate` has no live
// source in this repo, so they are typed config with these defaults.
// `ytdRevenue` IS available live (the summary API, RBAC-scoped) and is wired below;
// the constant is the documented value for a static/demo card.
// TODO: wire `target` / `targetDate` to a live company-goal source if one is added.
export const DEFAULT_TARGET = 100_000_000;
export const DEFAULT_YTD_REVENUE = 35_610_500;
export const DEFAULT_TARGET_DATE = "Dec 31, 2026";

interface RevenueTargetProgressProps {
  /** Yearly revenue goal (USD). */
  target?: number;
  /** Target date label shown to the user. */
  targetDate?: string;
  /** Optional override. When omitted, live year-to-date revenue (RBAC-scoped) is used. */
  ytdRevenue?: number;
}

/** Year-to-date range, org-wide within the caller's RBAC scope (ignores the global
 *  filter bar, like the per-period progress donuts — progress-to-annual-target is a
 *  whole-year figure, not a filtered slice). */
function ytdFilters(now: Date): Filters {
  return {
    ...defaultFilters(),
    preset: "custom",
    dateFrom: format(startOfYear(now), "yyyy-MM-dd"),
    dateTo: format(now, "yyyy-MM-dd"),
  };
}

function Figure({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border-faint pb-2 last:border-0 last:pb-0">
      <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </span>
      <span className="font-display text-lg tabular-nums">{value}</span>
    </div>
  );
}

/** "Revenue Progress to $100M Target" — a circular progress ring plus YTD revenue,
 *  remaining-to-target, and target date. Percentage and remaining are DERIVED from
 *  `target` and `ytdRevenue` so they can never disagree on screen. */
export function RevenueTargetProgress({
  target = DEFAULT_TARGET,
  targetDate = DEFAULT_TARGET_DATE,
  ytdRevenue,
}: RevenueTargetProgressProps) {
  const now = useMemo(() => new Date(), []);
  const filters = useMemo(() => ytdFilters(now), [now]);
  const summary = useSummary(filters);

  const liveYtd = summary.data?.current?.total_revenue_usd;
  const wired = ytdRevenue === undefined; // wired to live data unless overridden
  const isLoading = wired && summary.isLoading;
  const isError = wired && summary.isError;
  // Loaded but no revenue field => caller lacks the profitability metric group (RBAC).
  const rbacDenied = wired && summary.isSuccess && typeof liveYtd !== "number";

  const ytd: number | undefined = ytdRevenue ?? (typeof liveYtd === "number" ? liveYtd : undefined);

  // Single source of truth: everything below is derived, never stored separately.
  const hasValue = typeof ytd === "number" && target > 0;
  const pct = hasValue ? (ytd as number) / target : 0;
  const remaining = hasValue ? target - (ytd as number) : target;
  const exceeded = hasValue && (ytd as number) >= target;
  const ringColor = exceeded ? token("--color-positive") : token("--chart-grad-from");

  const ringOption: EChartsOption = {
    series: [
      {
        type: "pie",
        radius: ["64%", "82%"],
        center: ["50%", "50%"],
        silent: true,
        label: { show: false },
        data: hasValue
          ? [
              // Cap the fill at 100% (no overflow); the center still shows the true pct.
              { value: Math.min(ytd as number, target), itemStyle: { color: ringColor } },
              { value: Math.max(target - (ytd as number), 0), itemStyle: { color: token("--color-bg-elevated") } },
            ]
          : [{ value: 1, itemStyle: { color: token("--color-bg-elevated") } }],
      },
    ],
  };

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>
          Revenue Progress to {formatUSD(target, { compact: true })} Target
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
          <div className="relative h-[180px] w-[180px] shrink-0">
            <Chart option={ringOption} height={180} loading={isLoading} error={isError} />
            {!isLoading && !isError && (
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
                <span
                  className="text-2xl font-semibold tabular-nums"
                  style={exceeded ? { color: "var(--color-positive)" } : undefined}
                >
                  {hasValue ? formatPercent(pct) : "—"}
                </span>
                {exceeded && (
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wide"
                    style={{ color: "var(--color-positive)" }}
                  >
                    Target exceeded
                  </span>
                )}
                <span className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                  of target
                </span>
              </div>
            )}
          </div>

          <div className="w-full flex-1 space-y-3">
            {isLoading ? (
              <>
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </>
            ) : (
              <>
                <Figure
                  label="YTD Revenue"
                  value={hasValue ? formatUSD(ytd as number, { compact: true }) : "—"}
                />
                <Figure
                  label="Remaining to Target"
                  value={hasValue ? formatUSD(remaining, { compact: true }) : "—"}
                />
                <Figure label="Target Date" value={targetDate} />
              </>
            )}
            {rbacDenied && (
              <p className="text-[11px] text-muted-foreground">
                Revenue is outside your access.
              </p>
            )}
            {isError && (
              <p className="text-[11px] text-[color:var(--color-negative)]">
                Couldn&apos;t load revenue.
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

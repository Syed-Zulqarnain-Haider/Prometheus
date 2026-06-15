"use client";

import { endOfMonth, endOfYear, format, startOfMonth, startOfYear } from "date-fns";
import { useMemo } from "react";

import { Chart } from "@/components/charts/chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSummary, useTargets } from "@/lib/api-hooks";
import { token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import { defaultFilters, type Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

export type ProgressPeriod = "year" | "month";

interface PeriodConfig {
  revenueLabel: string;
  defaultTarget: number;
  rangeStart: (now: Date) => Date;
  defaultTargetDate: (now: Date) => string;
  defaultTitle: (target: number) => string;
}

// The $100M goal's deadline year. The yearly target date is fixed to this year's
// end (NOT the browser's current year), so it never shows the wrong year. Bump this
// (or override via the `targetDate` prop) when the goal's horizon changes.
const YEARLY_TARGET_YEAR = 2026;

// Per-period config. The REVENUE figure is wired live (the RBAC-scoped summary API).
// Targets have no confirmed live source here, so they are config (see notes below).
const PERIOD_CONFIG: Record<ProgressPeriod, PeriodConfig> = {
  year: {
    revenueLabel: "YTD Revenue",
    // Fixed $100M strategic goal (no live source). Override via the `target` prop.
    defaultTarget: 100_000_000,
    rangeStart: startOfYear,
    // Fixed deadline: Dec 31 of the goal's target year (e.g. "Dec 31, 2026") — not a
    // rolling year-end. Overridable via the `targetDate` prop.
    defaultTargetDate: () => format(endOfYear(new Date(YEARLY_TARGET_YEAR, 0, 1)), "MMM d, yyyy"),
    defaultTitle: (target) => `Revenue Progress to ${formatUSD(target, { compact: true })} Target`,
  },
  month: {
    revenueLabel: "MTD Revenue",
    // FALLBACK only — 8,333,333 (≈ $100M / 12) is used when no admin-set monthly
    // target exists for the current month. The live monthly target is wired in
    // MonthlyRevenueTargetProgress (from revenue_targets via /meta/targets).
    defaultTarget: 8_333_333,
    rangeStart: startOfMonth,
    // Last day of the CURRENT month, computed at render so it rolls forward monthly.
    defaultTargetDate: (now) => format(endOfMonth(now), "MMM d, yyyy"),
    defaultTitle: () => "Revenue Progress to Monthly Target",
  },
};

interface RevenueTargetProgressProps {
  /** Which period to track. Defaults to the yearly ($100M) view. */
  period?: ProgressPeriod;
  /** Revenue goal (USD) for the period. Defaults per period (see PERIOD_CONFIG). */
  target?: number;
  /** Target date label. Defaults to the period end, computed at render. */
  targetDate?: string;
  /** Title override. Defaults per period. */
  title?: string;
  /** Revenue override. When omitted, live period-to-date revenue (RBAC-scoped) is used.
   *  Documented placeholder for a static card: 0. */
  revenue?: number;
  /** Optional muted note under the figures (e.g. surfacing a fallback target). */
  targetNote?: string;
}

/** Range from the period start to today, org-wide within the caller's RBAC scope
 *  (ignores the global filter bar — progress-to-target is a whole-period figure). */
function rangeFilters(from: Date, to: Date): Filters {
  return {
    ...defaultFilters(),
    preset: "custom",
    dateFrom: format(from, "yyyy-MM-dd"),
    dateTo: format(to, "yyyy-MM-dd"),
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

/** Period-agnostic "Revenue Progress to Target" widget: a circular progress ring plus
 *  three figures — period-to-date revenue, remaining-to-target, and target date.
 *  Percentage and remaining are DERIVED from `target` and the resolved revenue, so
 *  they can never disagree on screen. Used for both the yearly and monthly instances. */
export function RevenueTargetProgress({
  period = "year",
  target,
  targetDate,
  title,
  revenue,
  targetNote,
}: RevenueTargetProgressProps) {
  const cfg = PERIOD_CONFIG[period];
  const now = useMemo(() => new Date(), []);

  const resolvedTarget = target ?? cfg.defaultTarget;
  const resolvedTargetDate = targetDate ?? cfg.defaultTargetDate(now);
  const resolvedTitle = title ?? cfg.defaultTitle(resolvedTarget);

  const filters = useMemo(() => rangeFilters(cfg.rangeStart(now), now), [cfg, now]);
  const summary = useSummary(filters);

  const liveRevenue = summary.data?.current?.total_revenue_usd;
  const wired = revenue === undefined; // wired to live data unless overridden
  const isLoading = wired && summary.isLoading;
  const isError = wired && summary.isError;
  // Loaded but no revenue field => caller lacks the profitability metric group (RBAC).
  const rbacDenied = wired && summary.isSuccess && typeof liveRevenue !== "number";

  const value: number | undefined =
    revenue ?? (typeof liveRevenue === "number" ? liveRevenue : undefined);

  // Single source of truth: everything below is derived, never stored separately.
  const hasValue = typeof value === "number" && resolvedTarget > 0;
  const pct = hasValue ? (value as number) / resolvedTarget : 0;
  const remaining = hasValue ? resolvedTarget - (value as number) : resolvedTarget;
  const exceeded = hasValue && (value as number) >= resolvedTarget;
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
              { value: Math.min(value as number, resolvedTarget), itemStyle: { color: ringColor } },
              {
                value: Math.max(resolvedTarget - (value as number), 0),
                itemStyle: { color: token("--color-bg-elevated") },
              },
            ]
          : [{ value: 1, itemStyle: { color: token("--color-bg-elevated") } }],
      },
    ],
  };

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>{resolvedTitle}</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Container-responsive (flex-wrap), NOT viewport-gated: the metrics panel
            sits to the right of the ring whenever the CELL is wide enough, and wraps
            cleanly below it when narrow — so a narrow react-grid cell never clips or
            hides it (matches the reference: ring left, three rows right). */}
        <div className="flex flex-wrap items-center gap-6">
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

          <div className="min-w-[220px] flex-1 space-y-3">
            {isLoading ? (
              <>
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </>
            ) : (
              <>
                <Figure
                  label={cfg.revenueLabel}
                  value={hasValue ? formatUSD(value as number, { compact: true }) : "—"}
                />
                <Figure
                  label="Remaining to Target"
                  value={hasValue ? formatUSD(remaining, { compact: true }) : "—"}
                />
                <Figure label="Target Date" value={resolvedTargetDate} />
              </>
            )}
            {targetNote && !isLoading && (
              <p className="text-[11px] text-muted-foreground">{targetNote}</p>
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

/** Monthly instance wired to the real admin-set monthly target from `revenue_targets`
 *  (via `useTargets` → `/api/v1/meta/targets`), the same source the existing
 *  RevenueProgress donut reads. If no target row exists for the current month, it
 *  falls back to the component's default and surfaces that with a note — it never
 *  crashes. The yearly instance is untouched. */
export function MonthlyRevenueTargetProgress() {
  const now = useMemo(() => new Date(), []);
  const { data, isSuccess } = useTargets(now.getFullYear());

  const adminMonthlyTarget = data?.monthly.find(
    (m) => m.period_month === now.getMonth() + 1,
  )?.target_usd;
  // Only surface the fallback once the targets query has resolved (avoid a flash).
  const usingFallback = isSuccess && adminMonthlyTarget === undefined;

  return (
    <RevenueTargetProgress
      period="month"
      // undefined => the component uses its own monthly fallback target.
      target={adminMonthlyTarget}
      targetNote={usingFallback ? "Default target — set this month's target in Admin." : undefined}
    />
  );
}

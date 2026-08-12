"use client";

import {
  endOfMonth,
  endOfYear,
  format,
  getDayOfYear,
  getDaysInYear,
  startOfMonth,
  startOfYear,
} from "date-fns";
import { useMemo } from "react";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { usePacing, useSummary, useTargets } from "@/lib/api-hooks";
import { token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import { defaultFilters, type Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

type Period = "year" | "month";

function rangeFilters(from: Date, to: Date): Filters {
  return {
    ...defaultFilters(),
    preset: "custom",
    dateFrom: format(from, "yyyy-MM-dd"),
    dateTo: format(to, "yyyy-MM-dd"),
  };
}

/** One labeled metric row: label left, value right. */
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

/** Revenue-progress donut for one period. Shows actual / admin-set target (scoped to
 *  the caller, from the summary API) once that period's target exists; otherwise an
 *  honest "target not set" state - progress is never faked.
 *
 *  Both cards render the SAME five rows (revenue, remaining, date, projection, pace) so
 *  the yearly and monthly cards are identical in size - the earlier version gave the
 *  monthly card two extra rows and the pair sat visibly lopsided on the Overview. The
 *  monthly projection comes from the pacing service; the yearly one is a linear
 *  run-rate (YTD / days elapsed x days in year), labeled as such.
 */
export function RevenueProgress({ period }: { period: Period }) {
  const now = useMemo(() => new Date(), []);
  const isYear = period === "year";

  const rangeStart = isYear ? startOfYear(now) : startOfMonth(now);
  const filters = useMemo(() => rangeFilters(rangeStart, now), [rangeStart, now]);

  const { data: targets } = useTargets(now.getFullYear());
  const summary = useSummary(filters);
  // Forward-looking pacing (projection + on/off-pace) for the monthly card.
  const pacing = usePacing(now.getFullYear(), now.getMonth() + 1);

  const target = isYear
    ? (targets?.annual?.target_usd ?? null)
    : (targets?.monthly.find((m) => m.period_month === now.getMonth() + 1)?.target_usd ?? null);

  const actual = summary.data?.current.total_revenue_usd ?? 0;
  const title = isYear ? "Yearly Progress to Target" : "Monthly Progress to Target";

  const targetSet = target !== null && target > 0;
  const pct = targetSet ? actual / (target as number) : 0;
  // Over-target: fill the whole ring (cap at 100%, no overflow) and switch to the
  // celebratory positive accent; the center label still shows the TRUE pct.
  const exceeded = targetSet && actual >= (target as number);
  const achieved = targetSet ? Math.min(actual, target as number) : 0;
  const remaining = targetSet ? Math.max((target as number) - actual, 0) : 1;
  const ringColor = exceeded ? token("--color-positive") : token("--chart-grad-from");

  // Projection + pace, one pair of values per period so both cards carry five rows.
  // Monthly comes from the pacing service; yearly is a linear run-rate, and days-elapsed
  // is never 0 (Jan 1 = day 1), so the division is safe.
  const projected = isYear
    ? (summary.data ? (actual / getDayOfYear(now)) * getDaysInYear(now) : null)
    : (pacing.data?.projected_usd ?? null);
  const pacePct = isYear
    ? (targetSet && projected != null ? projected / (target as number) : null)
    : (pacing.data?.pace_pct ?? null);

  const option: EChartsOption = {
    series: [
      {
        type: "pie",
        radius: ["64%", "82%"],
        center: ["50%", "50%"],
        silent: true,
        label: { show: false },
        data: targetSet
          ? [
              { value: achieved, itemStyle: { color: ringColor } },
              { value: remaining, itemStyle: { color: token("--color-bg-elevated") } },
            ]
          : [{ value: 1, itemStyle: { color: token("--color-bg-elevated") } }],
      },
    ],
  };

  // Period deadline shown in the "Target Date" row (end of the tracked period).
  const targetDate = format(isYear ? endOfYear(now) : endOfMonth(now), "MMM d, yyyy");

  return (
    <ChartCard title={title}>
      {/* Reference layout: ring on the LEFT, labeled rows on the RIGHT. h-full so the
          card stretches to its grid cell instead of floating at its content height -
          uneven card bottoms were what made the row read as badly spaced. */}
      <div className="flex h-full flex-wrap items-center gap-6">
        <div className="relative h-[180px] w-[180px] shrink-0">
          <Chart option={option} height={180} loading={summary.isLoading && targetSet} />
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            {targetSet ? (
              <>
                <span
                  className="text-2xl font-semibold tabular-nums"
                  style={exceeded ? { color: "var(--color-positive)" } : undefined}
                >
                  {formatPercent(pct)}
                </span>
                <span
                  className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground"
                  style={exceeded ? { color: "var(--color-positive)" } : undefined}
                >
                  Achieved
                </span>
              </>
            ) : (
              <span className="max-w-[7rem] text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Target not set
              </span>
            )}
          </div>
        </div>

        <div className="min-w-[220px] flex-1 space-y-3">
          <Figure
            label={isYear ? "YTD Revenue" : "MTD Revenue"}
            value={formatUSD(actual, { compact: true })}
          />
          <Figure
            label="Remaining to Target"
            value={targetSet ? formatUSD(remaining, { compact: true }) : ""}
          />
          <Figure label="Target Date" value={targetDate} />
          <Figure
            label={isYear ? "Projected (run-rate)" : "Projected (month-end)"}
            value={projected != null ? formatUSD(projected, { compact: true }) : "-"}
          />
          <Figure
            label="Pace vs plan"
            value={
              pacePct != null ? (
                <span
                  style={{
                    color: pacePct >= 1 ? "var(--color-positive)" : "var(--color-amber)",
                  }}
                >
                  {formatPercent(Math.abs(pacePct - 1))}
                  {pacePct >= 1 ? " ahead" : " behind"}
                </span>
              ) : (
                "-"
              )
            }
          />
          {!targetSet && (
            <p className="text-[11px] text-muted-foreground">
              Set the {period}ly target in Admin to track progress.
            </p>
          )}
        </div>
      </div>
    </ChartCard>
  );
}

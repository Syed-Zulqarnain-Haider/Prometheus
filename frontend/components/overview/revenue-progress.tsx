"use client";

import { format, startOfMonth, startOfYear } from "date-fns";
import { useMemo } from "react";

import { Chart } from "@/components/charts/chart";
import { ChartCard } from "@/components/charts/chart-card";
import { useSummary, useTargets } from "@/lib/api-hooks";
import { token } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import { defaultFilters, type Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

function rangeFilters(from: Date, to: Date): Filters {
  return { ...defaultFilters(), preset: "custom", dateFrom: format(from, "yyyy-MM-dd"), dateTo: format(to, "yyyy-MM-dd") };
}

/** Revenue-progress donut. Shows actual ÷ admin-set target once a target exists
 *  for the current period; otherwise an honest "target not set" state. Progress is
 *  computed from the API's revenue total (scoped to the caller) — never faked. */
export function RevenueProgress() {
  const now = useMemo(() => new Date(), []);
  const monthFilters = useMemo(() => rangeFilters(startOfMonth(now), now), [now]);
  const yearFilters = useMemo(() => rangeFilters(startOfYear(now), now), [now]);

  const { data: targets } = useTargets(now.getFullYear());
  const monthSummary = useSummary(monthFilters);
  const yearSummary = useSummary(yearFilters);

  const monthTarget = targets?.monthly.find((m) => m.period_month === now.getMonth() + 1)?.target_usd ?? null;
  const yearTarget = targets?.annual?.target_usd ?? null;

  // Prefer the monthly view when a monthly target exists; else fall back to annual.
  const useMonthly = monthTarget !== null;
  const target = useMonthly ? monthTarget : yearTarget;
  const summary = useMonthly ? monthSummary : yearSummary;
  const actual = summary.data?.current.total_revenue_usd ?? 0;
  const periodLabel = useMonthly ? format(now, "MMMM yyyy") : `FY ${now.getFullYear()}`;

  const targetSet = target !== null && target > 0;
  const pct = targetSet ? actual / (target as number) : 0;
  const achieved = targetSet ? Math.min(actual, target as number) : 0;
  const remaining = targetSet ? Math.max((target as number) - actual, 0) : 1;

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
              { value: achieved, itemStyle: { color: token("--chart-grad-from") } },
              { value: remaining, itemStyle: { color: token("--color-bg-elevated") } },
            ]
          : [{ value: 1, itemStyle: { color: token("--color-bg-elevated") } }],
      },
    ],
  };

  return (
    <ChartCard title="Revenue Progress to Target">
      <div className="relative">
        <Chart option={option} height={240} loading={summary.isLoading && targetSet} />
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          {targetSet ? (
            <div className="flex flex-col items-center text-center">
              <span className="text-2xl font-semibold tabular-nums">{formatPercent(pct)}</span>
              <span className="mt-1 text-[11px] leading-snug text-muted-foreground">
                {formatUSD(actual, { compact: true })} of {formatUSD(target, { compact: true })}
              </span>
              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                {periodLabel}
              </span>
            </div>
          ) : (
            <div className="flex max-w-[9rem] flex-col items-center text-center">
              <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Target
                <br />
                not set
              </span>
              <span className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
                Set targets in Admin to track progress.
              </span>
            </div>
          )}
        </div>
      </div>
    </ChartCard>
  );
}

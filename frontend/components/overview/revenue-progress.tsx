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

type Period = "year" | "month";

function rangeFilters(from: Date, to: Date): Filters {
  return {
    ...defaultFilters(),
    preset: "custom",
    dateFrom: format(from, "yyyy-MM-dd"),
    dateTo: format(to, "yyyy-MM-dd"),
  };
}

/** Revenue-progress donut for one period. Shows actual ÷ admin-set target (scoped to
 *  the caller, from the summary API) once that period's target exists; otherwise an
 *  honest "target not set" state — progress is never faked. */
export function RevenueProgress({ period }: { period: Period }) {
  const now = useMemo(() => new Date(), []);
  const isYear = period === "year";

  const rangeStart = isYear ? startOfYear(now) : startOfMonth(now);
  const filters = useMemo(() => rangeFilters(rangeStart, now), [rangeStart, now]);

  const { data: targets } = useTargets(now.getFullYear());
  const summary = useSummary(filters);

  const target = isYear
    ? (targets?.annual?.target_usd ?? null)
    : (targets?.monthly.find((m) => m.period_month === now.getMonth() + 1)?.target_usd ?? null);

  const actual = summary.data?.current.total_revenue_usd ?? 0;
  const title = isYear ? "Yearly Progress to Target" : "Monthly Progress to Target";
  const periodLabel = isYear ? `FY ${now.getFullYear()}` : format(now, "MMMM yyyy");

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
    <ChartCard title={title}>
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
                Set the {period}ly target in Admin to track progress.
              </span>
            </div>
          )}
        </div>
      </div>
    </ChartCard>
  );
}

"use client";

import { format, parseISO, subYears } from "date-fns";
import { useMemo, useState } from "react";

import { DateRangePicker } from "@/components/filters/date-range-picker";
import { KpiRow } from "@/components/overview/kpi-row";
import { RatioCards } from "@/components/overview/ratio-cards";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { COMPARE_METRICS, formatMetricValue } from "@/components/compare/metrics";
import { TopAppsCompare } from "@/components/compare/top-apps-compare";
import { useSummary } from "@/lib/api-hooks";
import { previousWindow } from "@/lib/compare";
import type { Filters } from "@/lib/filters";
import { formatPercent } from "@/lib/format";
import { useFilters } from "@/lib/use-filters";
import { cn } from "@/lib/utils";

/** How Period B is derived. The two presets FOLLOW Period A as it changes; picking a range
 *  by hand switches to custom and stays put. */
type BaselineMode = "previous" | "lastyear" | "custom";

function pretty(dateIso: string): string {
  return format(parseISO(dateIso), "d MMM yyyy");
}

function shiftYear(dateIso: string): string {
  return format(subYears(parseISO(dateIso), 1), "yyyy-MM-dd");
}

/** One side of the split: its own date picker on top, then the same KPI + ratio cards the
 *  Overview uses, fed a date-overridden copy of the global filters. */
function PeriodPanel({
  title,
  hint,
  filters,
  onRangeChange,
  actions,
}: {
  title: string;
  hint: string;
  filters: Filters;
  onRangeChange: (value: {
    preset: Filters["preset"];
    dateFrom: string;
    dateTo: string;
    compare: boolean;
  }) => void;
  actions?: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
              {title}
            </CardTitle>
            <p className="text-xs text-muted-foreground">{hint}</p>
          </div>
          {actions}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DateRangePicker
            preset={filters.preset}
            dateFrom={filters.dateFrom}
            dateTo={filters.dateTo}
            compare={false}
            onChange={onRangeChange}
          />
          <span className="text-xs text-muted-foreground">
            {pretty(filters.dateFrom)} to {pretty(filters.dateTo)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <KpiRow filters={filters} />
        <RatioCards filters={filters} />
      </CardContent>
    </Card>
  );
}

/** Split-screen period comparison.
 *
 *  Period A is the global date range (the bar above and the left picker edit the same
 *  state). Period B defaults to the immediately-preceding window and keeps FOLLOWING
 *  Period A until a custom range is picked, so changing A never silently compares
 *  against a stale B. Dimension filters (apps, pods, platform, ...) apply to BOTH
 *  sides - the comparison isolates the date range, which is the whole point.
 */
export function CompareClient() {
  const { filters, setFilters } = useFilters();
  const [mode, setMode] = useState<BaselineMode>("previous");
  const [customRange, setCustomRange] = useState<{ from: string; to: string } | null>(null);

  const baseline = useMemo(() => {
    if (mode === "custom" && customRange) return customRange;
    if (mode === "lastyear") {
      return { from: shiftYear(filters.dateFrom), to: shiftYear(filters.dateTo) };
    }
    return previousWindow(filters.dateFrom, filters.dateTo);
  }, [mode, customRange, filters.dateFrom, filters.dateTo]);

  // compare:false on both sides - each panel is a single period; the ghost overlays would
  // double-fetch and muddy the split.
  const leftFilters = useMemo<Filters>(() => ({ ...filters, compare: false }), [filters]);
  const rightFilters = useMemo<Filters>(
    () => ({
      ...filters,
      preset: "custom",
      dateFrom: baseline.from,
      dateTo: baseline.to,
      compare: false,
    }),
    [filters, baseline],
  );

  const left = useSummary(leftFilters);
  const right = useSummary(rightFilters);
  const a = left.data?.current ?? {};
  const b = right.data?.current ?? {};
  const loading = left.isLoading || right.isLoading;

  // Only metrics at least one side actually returned (RBAC-safe, sparse-data-safe).
  const visibleRows = COMPARE_METRICS.filter(
    (r) => a[r.field] !== null && a[r.field] !== undefined,
  ).concat(
    COMPARE_METRICS.filter(
      (r) =>
        (a[r.field] === null || a[r.field] === undefined) &&
        b[r.field] !== null &&
        b[r.field] !== undefined,
    ),
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <PeriodPanel
          title="Period A"
          hint="The global date range - the filter bar above edits the same thing."
          filters={leftFilters}
          onRangeChange={(value) => setFilters({ ...filters, ...value, compare: filters.compare })}
        />
        <PeriodPanel
          title="Period B"
          hint={
            mode === "previous"
              ? "Previous period - follows Period A."
              : mode === "lastyear"
                ? "Same range last year - follows Period A."
                : "Custom range - fixed until you change it."
          }
          filters={rightFilters}
          onRangeChange={(value) => {
            setCustomRange({ from: value.dateFrom, to: value.dateTo });
            setMode("custom");
          }}
          actions={
            <div className="flex gap-1">
              <Button
                size="sm"
                variant={mode === "previous" ? "default" : "outline"}
                onClick={() => setMode("previous")}
              >
                Previous period
              </Button>
              <Button
                size="sm"
                variant={mode === "lastyear" ? "default" : "outline"}
                onClick={() => setMode("lastyear")}
              >
                Last year
              </Button>
            </div>
          }
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
            A vs B
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto px-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2 text-left font-medium">Metric</th>
                <th className="px-4 py-2 text-right font-medium">
                  A · {pretty(leftFilters.dateFrom)} to {pretty(leftFilters.dateTo)}
                </th>
                <th className="px-4 py-2 text-right font-medium">
                  B · {pretty(rightFilters.dateFrom)} to {pretty(rightFilters.dateTo)}
                </th>
                <th className="px-4 py-2 text-right font-medium">Change (A - B)</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td className="px-4 py-6 text-center text-muted-foreground" colSpan={4}>
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && visibleRows.length === 0 && (
                <tr>
                  <td className="px-4 py-6 text-center text-muted-foreground" colSpan={4}>
                    No data for either period with the current filters.
                  </td>
                </tr>
              )}
              {!loading &&
                visibleRows.map((row) => {
                  const va = a[row.field] ?? null;
                  const vb = b[row.field] ?? null;
                  const both = va !== null && vb !== null;
                  const diff = both ? va - vb : null;
                  // Percent change is meaningless off a zero or missing baseline; percentage
                  // metrics show the difference in points instead of a % of a %.
                  const pct = both && vb !== 0 && row.kind !== "pct" ? diff! / Math.abs(vb) : null;
                  const improved = diff !== null && (row.goodWhenUp ? diff > 0 : diff < 0);
                  const worsened = diff !== null && (row.goodWhenUp ? diff < 0 : diff > 0);
                  return (
                    <tr key={row.field} className="border-b border-border-faint">
                      <td className="px-4 py-2">{row.label}</td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {formatMetricValue(va, row.kind)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {formatMetricValue(vb, row.kind)}
                      </td>
                      <td
                        className={cn(
                          "px-4 py-2 text-right tabular-nums",
                          improved && "text-[color:var(--color-positive)]",
                          worsened && "text-destructive",
                        )}
                      >
                        {diff === null ? (
                          "-"
                        ) : (
                          <>
                            {diff > 0 ? "+" : ""}
                            {row.kind === "pct"
                              ? `${formatPercent(diff)} pts`
                              : formatMetricValue(diff, row.kind)}
                            {pct !== null && (
                              <span className="ml-1 text-xs text-muted-foreground">
                                ({pct > 0 ? "+" : ""}
                                {formatPercent(pct)})
                              </span>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <TopAppsCompare filters={leftFilters} />
    </div>
  );
}

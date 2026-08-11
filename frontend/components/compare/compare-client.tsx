"use client";

import { format, parseISO, subYears } from "date-fns";
import { useMemo, useState } from "react";

import { DateRangePicker } from "@/components/filters/date-range-picker";
import { KpiRow } from "@/components/overview/kpi-row";
import { RatioCards } from "@/components/overview/ratio-cards";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

const BASELINE_OPTIONS: { value: BaselineMode; label: string; hint: string }[] = [
  {
    value: "previous",
    label: "Previous period",
    hint: "Previous period - follows Period A.",
  },
  {
    value: "lastyear",
    label: "Same period last year",
    hint: "Same range last year - follows Period A.",
  },
  {
    value: "custom",
    label: "Custom range",
    hint: "Custom range - fixed until you change it.",
  },
];

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
  warning,
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
  warning?: string;
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
        {warning && (
          <p className="rounded-md border border-[color:var(--color-warning,#d97706)] px-2 py-1.5 text-xs text-[color:var(--color-warning,#d97706)]">
            {warning}
          </p>
        )}
      </CardHeader>
      {/* The KPI/ratio grids size their columns off the VIEWPORT (md:/xl: breakpoints), but
          here they live in a half-width panel, so on a wide screen they render five columns
          into half the room and the figures overflow their cards. The cards read their type
          scale from CSS variables, so scaling those down for this subtree fixes the overflow
          without forking the shared components (and leaves the Overview untouched). */}
      <CardContent
        className="space-y-4 [&_*]:min-w-0"
        style={
          {
            "--fs-kpi": "clamp(0.95rem, 1.35vw, 1.45rem)",
            "--fs-stat": "clamp(0.95rem, 1.35vw, 1.45rem)",
          } as React.CSSProperties
        }
      >
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

  // A pinned custom range can end up identical to Period A (picking the same preset in
  // Period B's calendar does exactly that). Every delta then reads 0.0% and the page looks
  // broken rather than self-referential, so say so instead of rendering a wall of zeros.
  const sameRange =
    leftFilters.dateFrom === rightFilters.dateFrom && leftFilters.dateTo === rightFilters.dateTo;

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
      {/* Side by side only from 2xl up. At xl the two panels are ~640px each, which is
          narrower than the KPI grid's own xl (five-column) layout expects - stacking keeps
          every figure readable instead of clipping it. */}
      <div className="grid gap-4 2xl:grid-cols-2">
        <PeriodPanel
          title="Period A"
          hint="The global date range - the filter bar above edits the same thing."
          filters={leftFilters}
          onRangeChange={(value) => setFilters({ ...filters, ...value, compare: filters.compare })}
        />
        <PeriodPanel
          title="Period B"
          hint={BASELINE_OPTIONS.find((o) => o.value === mode)?.hint ?? ""}
          filters={rightFilters}
          warning={
            sameRange
              ? "Period B currently matches Period A, so every change below is zero. Pick a different baseline above or a different range."
              : undefined
          }
          onRangeChange={(value) => {
            setCustomRange({ from: value.dateFrom, to: value.dateTo });
            setMode("custom");
          }}
          actions={
            <Select
              value={mode}
              onValueChange={(value) => {
                const next = value as BaselineMode;
                // Switching TO custom pins whatever is on screen right now, so the panel
                // never jumps to an unrelated range the moment the mode changes.
                if (next === "custom" && !customRange) setCustomRange(baseline);
                setMode(next);
              }}
            >
              <SelectTrigger className="h-8 w-52" aria-label="Period B baseline">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BASELINE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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

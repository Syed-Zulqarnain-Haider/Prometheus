"use client";

import { useMemo, useState } from "react";

import { Chart } from "@/components/charts/chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTable, useTimeseries } from "@/lib/api-hooks";
import { bucketLabels, metricValues, num } from "@/lib/chart-helpers";
import type { EChartsOption } from "@/lib/echarts";
import type { Filters } from "@/lib/filters";
import { COMPARE_METRICS, formatMetricValue } from "@/components/compare/metrics";

/** Lines on the chart. More than five daily lines turns into spaghetti; the table below
 *  carries the longer tail. */
const CHART_APPS = 5;
const TABLE_APPS = 10;

/** Fixed palette so the legend chips and table dots match the chart series exactly,
 *  whatever the active ECharts theme. */
const COLORS = ["#4285f4", "#a142f4", "#fbbc04", "#ea4335", "#34a853"];

interface TopApp {
  key: string;
  name: string;
  total: number;
}

/** Per-app timeseries for one slot. React hooks cannot run in a loop, so the component
 *  calls this a fixed CHART_APPS times; an empty slot passes no metrics, which disables
 *  the query entirely rather than fetching garbage. */
function useAppSeries(filters: Filters, app: TopApp | undefined, metric: string) {
  return useTimeseries(
    { ...filters, apps: app ? [app.key] : [] },
    app ? [metric] : [],
    "day",
  );
}

/** AdMob-style "Top apps by <metric>": one line per top app over the period, with a metric
 *  picker, matching legend chips, and a top-10 table. Dimension filters and Period A's date
 *  range apply throughout - the widget answers "which apps drive this metric right now".
 */
export function TopAppsCompare({ filters }: { filters: Filters }) {
  const [metric, setMetric] = useState("total_revenue_usd");
  const meta = COMPARE_METRICS.find((m) => m.field === metric) ?? COMPARE_METRICS[0];

  // Top apps by the chosen metric - the same server-sorted table Apps Explorer uses.
  const table = useTable(filters, metric, TABLE_APPS);
  const apps = useMemo<TopApp[]>(
    () =>
      (table.data?.rows ?? []).map((row) => ({
        key: String(row.canonical_key ?? ""),
        name: String(row.app_name ?? row.canonical_key ?? "-"),
        total: num(row[metric]),
      })),
    [table.data, metric],
  );
  const chartApps = apps.slice(0, CHART_APPS);

  // Hooks must be called unconditionally and never in a loop - five fixed slots.
  const s0 = useAppSeries(filters, chartApps[0], metric);
  const s1 = useAppSeries(filters, chartApps[1], metric);
  const s2 = useAppSeries(filters, chartApps[2], metric);
  const s3 = useAppSeries(filters, chartApps[3], metric);
  const s4 = useAppSeries(filters, chartApps[4], metric);
  const series = [s0, s1, s2, s3, s4].slice(0, chartApps.length);

  const loading = table.isLoading || series.some((s) => s.isLoading);
  const error = table.isError || series.some((s) => s.isError);
  const labels = bucketLabels(series.find((s) => s.data)?.data);

  const option: EChartsOption = {
    color: COLORS,
    grid: { top: 12, bottom: 24, left: 8, right: 16, containLabel: true },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => formatMetricValue(Number(v), meta.kind),
    },
    xAxis: { type: "category", data: labels },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => formatMetricValue(v, meta.kind) },
    },
    series: chartApps.map((app, i) => ({
      name: app.name,
      type: "line" as const,
      showSymbol: false,
      data: metricValues(series[i]?.data, metric),
    })),
  };

  const grandTotal = apps.reduce((sum, app) => sum + app.total, 0);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
          Top apps by metric
        </CardTitle>
        <Select value={metric} onValueChange={setMetric}>
          <SelectTrigger className="h-8 w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {COMPARE_METRICS.map((m) => (
              <SelectItem key={m.field} value={m.field}>
                Top apps by {m.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Purpose-built multi-app line comparison - the house bar default would render
            five interleaved daily bar sets, which is unreadable, so this chart is fixed. */}
        <Chart
          option={option}
          loading={loading}
          error={error}
          isEmpty={!loading && chartApps.length === 0}
          emptyMessage="No apps have data for this metric in the selected period."
          height={300}
          adjustable={false}
        />

        {/* AdMob-style legend chips: colored dot + app + period total, matching the lines. */}
        {chartApps.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {chartApps.map((app, i) => (
              <span
                key={app.key}
                className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs"
              >
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: COLORS[i] }}
                  aria-hidden
                />
                <span className="max-w-[16rem] truncate">{app.name}</span>
                <span className="font-medium tabular-nums">
                  {formatMetricValue(app.total, meta.kind)}
                </span>
              </span>
            ))}
          </div>
        )}

        {apps.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2 text-left font-medium">#</th>
                  <th className="px-3 py-2 text-left font-medium">App</th>
                  <th className="px-3 py-2 text-right font-medium">{meta.label}</th>
                  <th className="px-3 py-2 text-right font-medium">Share of top {apps.length}</th>
                </tr>
              </thead>
              <tbody>
                {apps.map((app, i) => (
                  <tr key={app.key} className="border-b border-border-faint hover:bg-accent">
                    <td className="px-3 py-1.5 text-muted-foreground">{i + 1}</td>
                    <td className="px-3 py-1.5">
                      <span className="inline-flex items-center gap-2">
                        {i < CHART_APPS && (
                          <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ backgroundColor: COLORS[i] }}
                            aria-hidden
                          />
                        )}
                        <span className="max-w-[24rem] truncate">{app.name}</span>
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {formatMetricValue(app.total, meta.kind)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                      {grandTotal !== 0
                        ? `${((app.total / grandTotal) * 100).toFixed(1)}%`
                        : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

"use client";

import { X } from "lucide-react";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useBreakdown, useMe } from "@/lib/api-hooks";
import { num } from "@/lib/chart-helpers";
import { formatCompact, formatUSD } from "@/lib/format";
import { metricLabel, permittedMetricsByGroup } from "@/lib/report-metrics";
import type { MetricValue } from "@/lib/types";
import { useFilters } from "@/lib/use-filters";
import { cn } from "@/lib/utils";

const MAX_METRICS = 8;

const DIMENSIONS: { value: string; label: string }[] = [
  { value: "app", label: "App" },
  { value: "pod", label: "Pod" },
  { value: "publisher", label: "Publisher" },
  { value: "platform", label: "Platform" },
  { value: "hou", label: "HOU" },
];

function fmt(name: string, v: MetricValue | undefined): string {
  const n = num(v);
  return name.endsWith("_usd") ? formatUSD(n, { compact: true }) : formatCompact(n);
}

/** Explore: a fully user-configurable breakdown — pick the DIMENSION and the METRICS from
 *  dropdowns (every permitted measure, including the reported rpt_* ladder). The global
 *  filter bar (dates + all dimension dropdowns) applies, and RBAC still rules: only the
 *  caller's permitted metrics are offered, and the server re-validates every request. */
export function ExploreClient() {
  const { filters } = useFilters();
  const { data: me } = useMe();

  const groups = useMemo(
    () => permittedMetricsByGroup(me?.metric_groups ?? []),
    [me?.metric_groups],
  );
  const allPermitted = useMemo(
    () => new Set(groups.flatMap((g) => g.metrics.map((m) => m.name))),
    [groups],
  );

  const [dimension, setDimension] = useState("app");
  const [metrics, setMetrics] = useState<string[]>([]);

  // Sensible default once permissions load: reported revenue if visible, else revenue,
  // else installs — the user changes everything from the dropdowns anyway.
  const effectiveMetrics = useMemo(() => {
    if (metrics.length > 0) return metrics.filter((m) => allPermitted.has(m));
    const defaults = [
      "rpt_total_revenue_usd",
      "total_revenue_usd",
      "total_ua_spend_usd",
      "store_total_installs",
    ].filter((m) => allPermitted.has(m));
    return defaults.slice(0, 2);
  }, [metrics, allPermitted]);

  const query = useBreakdown(filters, dimension, effectiveMetrics);
  const rows = query.data?.rows ?? [];
  const dimLabel = DIMENSIONS.find((d) => d.value === dimension)?.label ?? dimension;

  function addMetric(name: string) {
    setMetrics((prev) => {
      const base = prev.length > 0 ? prev : effectiveMetrics;
      if (base.includes(name) || base.length >= MAX_METRICS) return base;
      return [...base, name];
    });
  }
  function removeMetric(name: string) {
    setMetrics((prev) => (prev.length > 0 ? prev : effectiveMetrics).filter((m) => m !== name));
  }

  const addable = groups
    .map((g) => ({
      ...g,
      metrics: g.metrics.filter((m) => !effectiveMetrics.includes(m.name)),
    }))
    .filter((g) => g.metrics.length > 0);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Explore"
        description="Pick any dimension and any of your permitted metrics — including the reported (rpt) figures."
      />

      {/* Dimension + metric pickers */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 py-4">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Dimension
            </span>
            <Select value={dimension} onValueChange={setDimension}>
              <SelectTrigger className="h-8 w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DIMENSIONS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>
                    {d.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Add metric
            </span>
            <Select value="" onValueChange={addMetric}>
              <SelectTrigger className="h-8 w-64">
                <SelectValue
                  placeholder={
                    effectiveMetrics.length >= MAX_METRICS
                      ? `Max ${MAX_METRICS} metrics`
                      : "Choose a metric…"
                  }
                />
              </SelectTrigger>
              <SelectContent className="max-h-80">
                {addable.map((g) => (
                  <div key={g.group}>
                    <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {g.label}
                    </div>
                    {g.metrics.map((m) => (
                      <SelectItem key={m.name} value={m.name}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </div>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Selected metrics as removable chips */}
          <div className="flex flex-wrap items-center gap-1.5">
            {effectiveMetrics.map((m) => (
              <span
                key={m}
                className="inline-flex items-center gap-1 rounded-full border bg-muted px-2.5 py-1 text-xs"
              >
                {metricLabel(m)}
                {effectiveMetrics.length > 1 && (
                  <button
                    type="button"
                    aria-label={`Remove ${metricLabel(m)}`}
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => removeMetric(m)}
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </span>
            ))}
            {metrics.length > 0 && (
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setMetrics([])}>
                Reset
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Result table — sorted by the FIRST metric (server-side, descending) */}
      <Card>
        <CardContent className="px-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="whitespace-nowrap px-3 py-2 text-left font-medium">{dimLabel}</th>
                  {effectiveMetrics.map((m, i) => (
                    <th key={m} className="whitespace-nowrap px-3 py-2 text-right font-medium">
                      {metricLabel(m)}
                      {i === 0 && <span className="ml-1">▼</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {query.isLoading &&
                  Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i} className="border-b border-border-faint">
                      <td className="px-3 py-2" colSpan={1 + effectiveMetrics.length}>
                        <Skeleton className="h-4 w-full" />
                      </td>
                    </tr>
                  ))}
                {!query.isLoading && query.isError && (
                  <tr>
                    <td
                      className="px-3 py-6 text-center text-[color:var(--color-negative)]"
                      colSpan={1 + effectiveMetrics.length}
                    >
                      Couldn&apos;t load — please retry (a metric may not be permitted).
                    </td>
                  </tr>
                )}
                {!query.isLoading && !query.isError && rows.length === 0 && (
                  <tr>
                    <td
                      className="px-3 py-6 text-center text-muted-foreground"
                      colSpan={1 + effectiveMetrics.length}
                    >
                      No data for the selected filters
                    </td>
                  </tr>
                )}
                {rows.map((row, i) => (
                  <tr key={i} className="border-b border-border-faint hover:bg-accent">
                    <td className="whitespace-nowrap px-3 py-2 font-medium">
                      {String(
                        (dimension === "app" ? (row.app_name ?? row.app) : row[dimension]) ?? "—",
                      )}
                    </td>
                    {effectiveMetrics.map((m) => (
                      <td
                        key={m}
                        className={cn("whitespace-nowrap px-3 py-2 text-right tabular-nums")}
                      >
                        {fmt(m, row[m])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

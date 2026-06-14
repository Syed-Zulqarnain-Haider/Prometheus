"use client";

import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useBreakdown, useCreateReport, useMe, useTimeseries } from "@/lib/api-hooks";
import { filtersToApiQuery } from "@/lib/filters";
import { metricLabel, permittedMetricsByGroup } from "@/lib/report-metrics";
import type { ReportGroupBy } from "@/lib/types";
import { useFilters } from "@/lib/use-filters";

const GROUP_BY_OPTIONS: { value: ReportGroupBy; label: string }[] = [
  { value: "app", label: "App" },
  { value: "pod", label: "Pod" },
  { value: "publisher", label: "Publisher" },
  { value: "platform", label: "Platform" },
  { value: "hou", label: "House" },
  { value: "date", label: "Date" },
];

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  return String(value);
}

/** Compose a report from the metrics the caller is permitted to see, preview it
 *  live (through the caller's own RBAC), and save it for reuse / sharing. */
export function ReportBuilder() {
  const { filters } = useFilters();
  const { data: me } = useMe();
  const createReport = useCreateReport();

  const [name, setName] = useState("");
  const [groupBy, setGroupBy] = useState<ReportGroupBy>("app");
  const [columns, setColumns] = useState<string[]>([]);

  const groups = useMemo(
    () => permittedMetricsByGroup(me?.metric_groups ?? []),
    [me?.metric_groups],
  );

  const isDate = groupBy === "date";
  // Preview reuses the metrics endpoints — same RBAC-scoped path the report runs.
  const breakdown = useBreakdown(filters, groupBy, isDate ? [] : columns);
  const timeseries = useTimeseries(filters, isDate ? columns : [], "day");
  const preview = isDate ? timeseries.data : breakdown.data;
  const previewRows = isDate
    ? (timeseries.data?.series ?? [])
    : (breakdown.data?.rows ?? []);
  const dimensionKey = isDate ? "bucket" : groupBy;

  function toggleColumn(metric: string) {
    setColumns((current) =>
      current.includes(metric)
        ? current.filter((c) => c !== metric)
        : [...current, metric],
    );
  }

  function save() {
    const trimmed = name.trim();
    if (!trimmed || columns.length === 0) return;
    createReport.mutate(
      {
        name: trimmed,
        filters: filtersToApiQuery(filters) as unknown as Record<string, unknown>,
        columns,
        group_by: groupBy,
      },
      { onSuccess: () => setName("") },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Report builder</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="report-name">Name</Label>
            <Input
              id="report-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Weekly installs by pod"
              className="w-64"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="report-groupby">Group by</Label>
            <Select value={groupBy} onValueChange={(value) => setGroupBy(value as ReportGroupBy)}>
              <SelectTrigger id="report-groupby" className="h-9 w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GROUP_BY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={save} disabled={!name.trim() || columns.length === 0 || createReport.isPending}>
            {createReport.isPending ? "Saving…" : "Save report"}
          </Button>
        </div>

        {createReport.isError && (
          <p className="text-xs text-destructive">
            {createReport.error instanceof Error
              ? createReport.error.message
              : "Could not save the report."}
          </p>
        )}

        <div className="space-y-2">
          <Label>Metrics</Label>
          {groups.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Your role has no metrics available to report on.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {groups.map((group) => (
                <div key={group.group} className="space-y-1">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {group.label}
                  </p>
                  {group.metrics.map((metric) => (
                    <label
                      key={metric.name}
                      className="flex cursor-pointer items-center gap-2 text-sm"
                    >
                      <Checkbox
                        checked={columns.includes(metric.name)}
                        onCheckedChange={() => toggleColumn(metric.name)}
                      />
                      {metric.label}
                    </label>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Label>Preview</Label>
            {columns.length > 0 && (
              <Badge variant="secondary">{columns.length} metric(s)</Badge>
            )}
          </div>
          {columns.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Select at least one metric to preview.
            </p>
          ) : !preview ? (
            <p className="text-xs text-muted-foreground">Loading preview…</p>
          ) : previewRows.length === 0 ? (
            <p className="text-xs text-muted-foreground">No rows for the current filters.</p>
          ) : (
            <div className="overflow-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">{isDate ? "Date" : groupBy}</th>
                    {columns.map((column) => (
                      <th key={column} className="px-3 py-2 text-right">
                        {metricLabel(column)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewRows.slice(0, 20).map((row, index) => (
                    <tr key={index} className="border-t">
                      <td className="px-3 py-1.5">{formatCell(row[dimensionKey])}</td>
                      {columns.map((column) => (
                        <td key={column} className="px-3 py-1.5 text-right tabular-nums">
                          {formatCell(row[column])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

"use client";

import Link from "next/link";
import { useMemo } from "react";

import {
  type ColumnDef,
  METRIC_COLUMNS,
  MetricTable,
  type Row,
  permittedMeasures,
} from "@/components/overview/revenue-table";
import { useBreakdown, useMe } from "@/lib/api-hooks";
import { num } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";

const UNASSIGNED = "Unassigned";

/** A NULL or blank ``hou`` maps to a single "Unassigned" bucket (never dropped), so HOU
 *  totals reconcile with the rest of the dashboard. */
function houKey(row: Row): string {
  const h = row.hou;
  return h == null || String(h).trim() === "" ? UNASSIGNED : String(h);
}

/** Single identity column — the HOU value, linked to its drill-down analytics page (a real
 *  HOU only; the "Unassigned" bucket has no page). One row per HOU. */
const HOU_IDENTITY: ColumnDef = {
  id: "hou",
  label: "HOU",
  requires: [],
  align: "left",
  fmt: "text",
  value: houKey,
  render: (r) => {
    const key = houKey(r);
    if (key === UNASSIGNED) return <span className="text-muted-foreground">{UNASSIGNED}</span>;
    return (
      <Link
        href={`/hou/${encodeURIComponent(key)}`}
        className="font-medium text-[color:var(--color-accent)] hover:underline"
      >
        {key}
      </Link>
    );
  },
};

/** Combine any rows sharing a HOU key (notably NULL + blank → one "Unassigned") by SUMMING
 *  the additive measures. Derived columns (ROAS, Gross, Net) are then recomputed by the
 *  shared column defs from these HOU-level totals — never averaged from per-row ratios. */
function mergeByHou(rows: Row[], measures: string[]): Row[] {
  const byKey = new Map<string, Row>();
  for (const row of rows) {
    const key = houKey(row);
    const existing = byKey.get(key);
    if (existing) {
      for (const m of measures) existing[m] = num(existing[m]) + num(row[m]);
    } else {
      const base: Row = { hou: key === UNASSIGNED ? null : key };
      for (const m of measures) base[m] = num(row[m]);
      byKey.set(key, base);
    }
  }
  return [...byKey.values()];
}

/** HOU Performance — the Publisher Performance table grouped by the ``hou`` dimension.
 *  Structurally identical (inherits METRIC_COLUMNS), one row per HOU (+ "Unassigned"),
 *  additive metrics summed server-side per HOU, ratios recomputed from those totals.
 *  Row-scope is enforced by the same breakdown scope injection the rest of the app uses. */
export function HouTable({ filters }: { filters: Filters }) {
  const { data: me } = useMe();
  const permitted = useMemo(() => permittedMeasures(me?.metric_groups ?? []), [me]);

  const columns = useMemo(
    () => [HOU_IDENTITY, ...METRIC_COLUMNS].filter((c) => c.requires.every((m) => permitted.has(m))),
    [permitted],
  );

  // Fetch exactly the additive measures the visible columns need (all already permitted,
  // so the breakdown's own metric-permission check passes).
  const measures = useMemo(
    () => [...new Set(columns.flatMap((c) => c.requires))],
    [columns],
  );

  const breakdown = useBreakdown(filters, "hou", measures);
  const rows = useMemo(
    () => mergeByHou(breakdown.data?.rows ?? [], measures),
    [breakdown.data, measures],
  );

  return (
    <MetricTable
      title="HOU Performance"
      columns={columns}
      rows={rows}
      rowKey={houKey}
      isLoading={breakdown.isLoading}
      isError={breakdown.isError}
    />
  );
}

"use client";

import Link from "next/link";
import { useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StoreLinkIcon } from "@/components/ui/store-link-icon";
import { useMe, useTable } from "@/lib/api-hooks";
import { num } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatCompact, formatMultiplier, formatUSD } from "@/lib/format";
import { REPORT_METRICS } from "@/lib/report-metrics";
import type { MetricValue } from "@/lib/types";

type Row = Record<string, MetricValue>;

/** The additive measures the caller may see, derived from their metric groups —
 *  the same authority the server enforces. A column is shown only if EVERY measure
 *  it needs is permitted, so a role without spend never sees UA Cost / Net Rev / ROAS. */
function permittedMeasures(groups: string[]): Set<string> {
  const allowed = new Set(groups);
  return new Set(REPORT_METRICS.filter((m) => allowed.has(m.group)).map((m) => m.name));
}

interface ColumnDef {
  id: string;
  label: string;
  requires: string[]; // measure names that must all be permitted to show the column
  align: "left" | "right";
  fmt: "usd" | "count" | "roas" | "text";
  value: (row: Row) => number | string | null;
}

// Left → right, mapped to the metric registry's existing fields. Derived columns
// (Gross Rev, Net Rev, ROAS) are computed per row from summed, permitted components.
const COLUMNS: ColumnDef[] = [
  { id: "publisher", label: "Publisher", requires: [], align: "left", fmt: "text",
    value: (r) => (r.publisher == null ? "—" : String(r.publisher)) },
  { id: "game", label: "Game", requires: [], align: "left", fmt: "text",
    value: (r) => String(r.app_name ?? r.canonical_key ?? "—") },
  { id: "installs", label: "Installs", requires: ["store_total_installs"], align: "right", fmt: "count",
    value: (r) => num(r.store_total_installs) },
  { id: "paid", label: "Paid Inst", requires: ["total_paid_installs"], align: "right", fmt: "count",
    value: (r) => num(r.total_paid_installs) },
  { id: "organic", label: "Organic Inst", requires: ["store_organic_installs"], align: "right", fmt: "count",
    value: (r) => num(r.store_organic_installs) },
  { id: "gross", label: "Gross Rev", requires: ["total_iap_gross_usd", "total_ad_revenue_usd"], align: "right", fmt: "usd",
    value: (r) => num(r.total_iap_gross_usd) + num(r.total_ad_revenue_usd) },
  { id: "iap", label: "IAP Rev", requires: ["total_iap_net_usd"], align: "right", fmt: "usd",
    value: (r) => num(r.total_iap_net_usd) },
  { id: "ua", label: "UA Cost", requires: ["total_ua_spend_usd"], align: "right", fmt: "usd",
    value: (r) => num(r.total_ua_spend_usd) },
  { id: "net", label: "Net Rev", requires: ["total_revenue_usd", "total_ua_spend_usd"], align: "right", fmt: "usd",
    value: (r) => num(r.total_revenue_usd) - num(r.total_ua_spend_usd) },
  { id: "roas", label: "ROAS", requires: ["total_revenue_usd", "total_ua_spend_usd"], align: "right", fmt: "roas",
    value: (r) => { const s = num(r.total_ua_spend_usd); return s > 0 ? num(r.total_revenue_usd) / s : null; } },
];

function format(col: ColumnDef, v: number | string | null): string {
  if (v == null) return "—";
  if (col.fmt === "text") return String(v);
  if (col.fmt === "usd") return formatUSD(v as number, { compact: true });
  if (col.fmt === "count") return formatCompact(v as number);
  return formatMultiplier(v as number);
}

/** Full-width per-game revenue table for the Overview. One row per app (game) with
 *  its publisher, RBAC-gated columns, compact formatting, sorted by Gross Rev desc.
 *  Horizontally scrolls within the card when space is tight. */
export function RevenueTable({ title, filters }: { title: string; filters: Filters }) {
  const { data: me } = useMe();
  const permitted = useMemo(() => permittedMeasures(me?.metric_groups ?? []), [me]);

  const columns = useMemo(
    () => COLUMNS.filter((c) => c.requires.every((m) => permitted.has(m))),
    [permitted],
  );
  // Default sort = Gross Rev desc; fall back to the first visible revenue/installs col.
  const sortCol =
    columns.find((c) => c.id === "gross") ??
    columns.find((c) => c.id === "net") ??
    columns.find((c) => c.id === "iap") ??
    columns.find((c) => c.id === "installs") ??
    null;

  // The table endpoint is keyset-sorted by a single permitted column; fetch a generous
  // superset, then sort client-side by the chosen key and take the top 10.
  const fetchSort = permitted.has("total_revenue_usd")
    ? "total_revenue_usd"
    : permitted.has("store_total_installs")
      ? "store_total_installs"
      : "canonical_key";
  const table = useTable(filters, fetchSort, 100);

  const rows = useMemo(() => {
    const data = table.data?.rows ?? [];
    return [...data]
      .sort((a, b) =>
        (sortCol ? Number(sortCol.value(b) ?? -Infinity) : 0) -
        (sortCol ? Number(sortCol.value(a) ?? -Infinity) : 0),
      )
      .slice(0, 10);
  }, [table.data, sortCol]);

  const span = columns.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
                {columns.map((c) => (
                  <th
                    key={c.id}
                    className={`whitespace-nowrap px-3 py-2 font-medium ${c.align === "right" ? "text-right" : "text-left"}`}
                  >
                    {c.label}
                    {sortCol?.id === c.id && <span className="ml-1">▼</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.isLoading &&
                Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-b border-border-faint">
                    <td className="px-3 py-2" colSpan={span}>
                      <Skeleton className="h-4 w-full" />
                    </td>
                  </tr>
                ))}
              {!table.isLoading && table.isError && (
                <tr>
                  <td className="px-3 py-6 text-center text-[color:var(--color-negative)]" colSpan={span}>
                    Couldn&apos;t load this table — please retry.
                  </td>
                </tr>
              )}
              {!table.isLoading && !table.isError && rows.length === 0 && (
                <tr>
                  <td className="px-3 py-6 text-center text-muted-foreground" colSpan={span}>
                    No data for the selected filters
                  </td>
                </tr>
              )}
              {rows.map((row) => {
                const ck = String(row.canonical_key ?? row.app_name ?? "");
                return (
                  <tr key={ck} className="border-b border-border-faint hover:bg-accent">
                    {columns.map((c) =>
                      c.id === "game" ? (
                        <td key={c.id} className="whitespace-nowrap px-3 py-2">
                          <span className="inline-flex items-center gap-1.5">
                            <Link
                              href={`/apps/${encodeURIComponent(ck)}`}
                              className="font-medium text-[color:var(--color-accent)] hover:underline"
                            >
                              {String(row.app_name ?? ck)}
                            </Link>
                            <StoreLinkIcon
                              androidPackage={row.android_package as string | null}
                              appleId={row.apple_id as number | null}
                            />
                          </span>
                        </td>
                      ) : (
                        <td
                          key={c.id}
                          className={`whitespace-nowrap px-3 py-2 ${c.align === "right" ? "text-right tabular-nums" : ""}`}
                        >
                          {format(c, c.value(row))}
                        </td>
                      ),
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

"use client";

import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTable } from "@/lib/api-hooks";
import { num } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatMultiplier, formatUSD } from "@/lib/format";

export function TopAppsTable({ filters }: { filters: Filters }) {
  const table = useTable(filters, "total_revenue_usd", 10);
  const rows = table.data?.rows ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Top Apps by Revenue</CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2 text-left font-medium">App</th>
              <th className="px-4 py-2 text-right font-medium">Revenue</th>
              <th className="px-4 py-2 text-right font-medium">Spend</th>
              <th className="px-4 py-2 text-right font-medium">ROAS</th>
            </tr>
          </thead>
          <tbody>
            {table.isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-border-faint">
                  <td className="px-4 py-2" colSpan={4}>
                    <Skeleton className="h-4 w-full" />
                  </td>
                </tr>
              ))}
            {!table.isLoading && rows.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-center text-muted-foreground" colSpan={4}>
                  No data for the selected filters
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const key = String(row.canonical_key);
              const revenue = num(row.total_revenue_usd);
              const spend = num(row.total_ua_spend_usd);
              const roas = spend > 0 ? revenue / spend : null;
              return (
                <tr key={key} className="border-b border-border-faint hover:bg-accent">
                  <td className="px-4 py-2">
                    <Link
                      href={`/apps/${encodeURIComponent(key)}`}
                      className="font-medium text-[color:var(--color-accent)] hover:underline"
                    >
                      {String(row.app_name ?? key)}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatUSD(revenue)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatUSD(spend)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {formatMultiplier(roas)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

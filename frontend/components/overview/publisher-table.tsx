"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBreakdown } from "@/lib/api-hooks";
import { num } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatMultiplier, formatUSD } from "@/lib/format";

export function PublisherTable({ filters }: { filters: Filters }) {
  const breakdown = useBreakdown(filters, "publisher", [
    "total_revenue_usd",
    "total_ua_spend_usd",
  ]);
  const rows = [...(breakdown.data?.rows ?? [])].sort(
    (a, b) => num(b.total_revenue_usd) - num(a.total_revenue_usd),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Publisher Performance</CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2 text-left font-medium">Publisher</th>
              <th className="px-4 py-2 text-right font-medium">Revenue</th>
              <th className="px-4 py-2 text-right font-medium">Spend</th>
              <th className="px-4 py-2 text-right font-medium">ROAS</th>
            </tr>
          </thead>
          <tbody>
            {breakdown.isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-border-faint">
                  <td className="px-4 py-2" colSpan={4}>
                    <Skeleton className="h-4 w-full" />
                  </td>
                </tr>
              ))}
            {!breakdown.isLoading && breakdown.isError && (
              <tr>
                <td
                  className="px-4 py-6 text-center text-[color:var(--color-negative)]"
                  colSpan={4}
                >
                  Couldn&apos;t load this table — please retry.
                </td>
              </tr>
            )}
            {!breakdown.isLoading && !breakdown.isError && rows.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-center text-muted-foreground" colSpan={4}>
                  No data for the selected filters
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const revenue = num(row.total_revenue_usd);
              const spend = num(row.total_ua_spend_usd);
              const roas = spend > 0 ? revenue / spend : null;
              return (
                <tr
                  key={String(row.publisher)}
                  className="border-b border-border-faint hover:bg-accent"
                >
                  <td className="px-4 py-2">{String(row.publisher ?? "—")}</td>
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

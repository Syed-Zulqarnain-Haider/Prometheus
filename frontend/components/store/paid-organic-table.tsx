"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBreakdown } from "@/lib/api-hooks";
import { num } from "@/lib/chart-helpers";
import type { Filters } from "@/lib/filters";
import { formatNumber, formatPercent } from "@/lib/format";

export function PaidOrganicTable({ filters }: { filters: Filters }) {
  const breakdown = useBreakdown(filters, "app", [
    "total_paid_installs",
    "store_organic_installs",
  ]);
  const rows = [...(breakdown.data?.rows ?? [])].sort(
    (a, b) =>
      num(b.total_paid_installs) +
      num(b.store_organic_installs) -
      (num(a.total_paid_installs) + num(a.store_organic_installs)),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Paid vs Organic by App</CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2 text-left font-medium">App</th>
              <th className="px-4 py-2 text-right font-medium">Paid</th>
              <th className="px-4 py-2 text-right font-medium">Organic</th>
              <th className="px-4 py-2 text-right font-medium">Organic %</th>
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
            {!breakdown.isLoading && rows.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-center text-muted-foreground" colSpan={4}>
                  No data for the selected filters
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const paid = num(row.total_paid_installs);
              const organic = num(row.store_organic_installs);
              const total = paid + organic;
              const share = total > 0 ? organic / total : null;
              return (
                <tr
                  key={String(row.app_name ?? row.app)}
                  className="border-b border-border-faint hover:bg-accent"
                >
                  <td className="px-4 py-2">{String(row.app_name ?? row.app ?? "—")}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatNumber(paid)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatNumber(organic)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{formatPercent(share)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

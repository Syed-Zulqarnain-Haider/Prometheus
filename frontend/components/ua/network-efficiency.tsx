"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSummary } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatPercent, formatUSD } from "@/lib/format";

const NETWORKS = [
  { label: "Facebook", spend: "fb_spend_usd", cpi: "fb_cpi", ctr: "fb_ctr" },
  { label: "Google Ads", spend: "gads_spend_usd", cpi: "gads_cpi", ctr: "gads_ctr" },
  { label: "Mintegral", spend: "mint_adv_spend_usd", cpi: "mint_adv_cpi", ctr: "mint_adv_ctr" },
];

export function NetworkEfficiency({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const current = summary.data?.current ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>CPI &amp; CTR by Network</CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2 text-left font-medium">Network</th>
              <th className="px-4 py-2 text-right font-medium">Spend</th>
              <th className="px-4 py-2 text-right font-medium">CPI</th>
              <th className="px-4 py-2 text-right font-medium">CTR</th>
            </tr>
          </thead>
          <tbody>
            {summary.isLoading &&
              NETWORKS.map((n) => (
                <tr key={n.label} className="border-b border-border-faint">
                  <td className="px-4 py-2" colSpan={4}>
                    <Skeleton className="h-4 w-full" />
                  </td>
                </tr>
              ))}
            {!summary.isLoading &&
              NETWORKS.map((n) => (
                <tr key={n.label} className="border-b border-border-faint">
                  <td className="px-4 py-2">{n.label}</td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {formatUSD(current[n.spend])}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {formatUSD(current[n.cpi], { digits: 2 })}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {formatPercent(current[n.ctr], 2)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

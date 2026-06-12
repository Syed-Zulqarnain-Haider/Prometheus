"use client";

import { Delta } from "@/components/overview/delta";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSummary } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import { formatMultiplier, formatUSD } from "@/lib/format";

export function RatioCards({ filters }: { filters: Filters }) {
  const summary = useSummary(filters);
  const current = summary.data?.current ?? {};
  const previous = summary.data?.previous ?? null;
  const loading = summary.isLoading;

  const ratios = [
    { label: "ROAS", field: "roas", value: formatMultiplier(current.roas) },
    { label: "Ad ROAS", field: "ad_roas", value: formatMultiplier(current.ad_roas) },
    { label: "CPI", field: "cpi", value: formatUSD(current.cpi, { digits: 2 }) },
  ];

  return (
    <div className="grid grid-cols-3 gap-4">
      {ratios.map((ratio) => (
        <Card key={ratio.field}>
          <CardContent className="pt-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {ratio.label}
            </div>
            {loading ? (
              <Skeleton className="mt-2 h-7 w-16" />
            ) : (
              <div className="mt-1 font-display text-[length:var(--fs-stat)] leading-tight">
                {ratio.value}
              </div>
            )}
            <div className="mt-1">
              <Delta current={current[ratio.field]} previous={previous?.[ratio.field]} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

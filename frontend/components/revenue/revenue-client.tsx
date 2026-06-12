"use client";

import { PageHeader } from "@/components/layout/page-header";
import { AdNetworkTrend } from "@/components/revenue/ad-network-trend";
import { DowHeatmap } from "@/components/revenue/dow-heatmap";
import { IapWaterfall } from "@/components/revenue/iap-waterfall";
import { RevenueDrill } from "@/components/revenue/revenue-drill";
import { useFilters } from "@/lib/use-filters";

export function RevenueClient() {
  const { filters } = useFilters();

  // Reset the drill path whenever the global filters change.
  const drillKey = [
    filters.dateFrom,
    filters.dateTo,
    filters.platform,
    filters.pods.join(","),
    filters.publishers.join(","),
    filters.apps.join(","),
  ].join("|");

  return (
    <div className="space-y-6">
      <PageHeader title="Revenue Analytics" />
      <RevenueDrill key={drillKey} filters={filters} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <IapWaterfall filters={filters} />
        <AdNetworkTrend filters={filters} />
      </div>
      <DowHeatmap filters={filters} />
    </div>
  );
}

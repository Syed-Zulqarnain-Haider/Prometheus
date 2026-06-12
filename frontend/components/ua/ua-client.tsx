"use client";

import { PageHeader } from "@/components/layout/page-header";
import { CpiVolumeScatter } from "@/components/ua/cpi-volume-scatter";
import { NetworkEfficiency } from "@/components/ua/network-efficiency";
import { SpendByNetwork } from "@/components/ua/spend-by-network";
import { SpendVsRevenue } from "@/components/ua/spend-vs-revenue";
import { useFilters } from "@/lib/use-filters";

export function UaClient() {
  const { filters } = useFilters();

  return (
    <div className="space-y-6">
      <PageHeader title="UA / Marketing" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SpendByNetwork filters={filters} />
        <NetworkEfficiency filters={filters} />
      </div>
      <SpendVsRevenue filters={filters} />
      <CpiVolumeScatter filters={filters} />
    </div>
  );
}

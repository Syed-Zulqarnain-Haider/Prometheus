"use client";

import { PageHeader } from "@/components/layout/page-header";
import { InstallMix } from "@/components/store/install-mix";
import { InstallsTrend } from "@/components/store/installs-trend";
import { PaidOrganicTable } from "@/components/store/paid-organic-table";
import { UninstallsRestores } from "@/components/store/uninstalls-restores";
import { useFilters } from "@/lib/use-filters";

export function StoreClient() {
  const { filters } = useFilters();

  return (
    <div className="space-y-6">
      <PageHeader title="Store Performance" />
      <InstallsTrend filters={filters} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <InstallMix filters={filters} />
        <UninstallsRestores filters={filters} />
      </div>
      <PaidOrganicTable filters={filters} />
    </div>
  );
}

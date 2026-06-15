"use client";

import { DemoSection } from "@/components/overview/demo-section";
import { KpiRow } from "@/components/overview/kpi-row";
import { MonthlyTrend } from "@/components/overview/monthly-trend";
import { PublisherTable } from "@/components/overview/publisher-table";
import { RatioCards } from "@/components/overview/ratio-cards";
import { RevenueComposition } from "@/components/overview/revenue-composition";
import { RevenueProgress } from "@/components/overview/revenue-progress";
import { RevenueVsSpend } from "@/components/overview/revenue-vs-spend";
import { PlatformSplit, PodSplit } from "@/components/overview/splits";
import { TopAppsTable } from "@/components/overview/top-apps-table";
import { PageHeader } from "@/components/layout/page-header";
import { useFilters } from "@/lib/use-filters";

export function OverviewClient() {
  const { filters } = useFilters();

  return (
    <div className="space-y-6">
      <PageHeader title="Executive Overview" />

      <KpiRow filters={filters} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <RevenueProgress period="year" />
        <div className="lg:col-span-2">
          <MonthlyTrend filters={filters} />
        </div>
        <RevenueProgress period="month" />
      </div>

      <RatioCards filters={filters} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RevenueVsSpend filters={filters} />
        <RevenueComposition filters={filters} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PlatformSplit filters={filters} />
        <PodSplit filters={filters} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PublisherTable filters={filters} />
        <TopAppsTable filters={filters} />
      </div>

      <DemoSection />
    </div>
  );
}

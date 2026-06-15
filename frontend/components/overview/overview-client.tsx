"use client";

import { LayoutGrid, RotateCcw } from "lucide-react";
import { useState } from "react";
import type { Layouts } from "react-grid-layout";

import { DashboardGrid } from "@/components/overview/dashboard-grid";
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
import { Button } from "@/components/ui/button";
import { defaultLayouts, type OverviewItemId } from "@/lib/overview-layout";
import { useFilters } from "@/lib/use-filters";

export function OverviewClient() {
  const { filters } = useFilters();
  const [editMode, setEditMode] = useState(false);
  // Layout lives in state only — no persistence in Phase 1 (resets on refresh).
  const [layouts, setLayouts] = useState<Layouts>(() => defaultLayouts());

  // The EXISTING widgets, wrapped untouched — each keeps its own data fetching,
  // filter reactivity, loading/empty/error states and RBAC. View mode and the
  // edit grid render the very same elements, just in a different container.
  const items: Record<OverviewItemId, React.ReactNode> = {
    kpis: <KpiRow filters={filters} />,
    "donut-year": <RevenueProgress period="year" />,
    trend: <MonthlyTrend filters={filters} />,
    "donut-month": <RevenueProgress period="month" />,
    ratios: <RatioCards filters={filters} />,
    "rev-vs-spend": <RevenueVsSpend filters={filters} />,
    composition: <RevenueComposition filters={filters} />,
    platform: <PlatformSplit filters={filters} />,
    pod: <PodSplit filters={filters} />,
    publisher: <PublisherTable filters={filters} />,
    "top-apps": <TopAppsTable filters={filters} />,
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader title="Executive Overview" />
        <div className="flex items-center gap-2">
          {editMode && (
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => setLayouts(defaultLayouts())}
            >
              <RotateCcw className="h-4 w-4" />
              Reset to default
            </Button>
          )}
          <Button
            variant={editMode ? "default" : "outline"}
            size="sm"
            className="gap-2"
            onClick={() => setEditMode((on) => !on)}
          >
            <LayoutGrid className="h-4 w-4" />
            {editMode ? "Done" : "Customize layout"}
          </Button>
        </div>
      </div>

      {editMode ? (
        // Edit mode: the draggable/resizable grid (default positions = the view below).
        <DashboardGrid items={items} layouts={layouts} onLayoutsChange={setLayouts} />
      ) : (
        // View mode: the default arrangement (mirrors the edit-grid default layout).
        <div className="space-y-6">
          {items.kpis}
          {/* Top row, three across: yearly donut | monthly trend | monthly donut.
              Stacks vertically below lg. */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {items["donut-year"]}
            {items.trend}
            {items["donut-month"]}
          </div>
          {/* Directly below: the two tables. */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {items.publisher}
            {items["top-apps"]}
          </div>
          {items.ratios}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {items["rev-vs-spend"]}
            {items.composition}
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {items.platform}
            {items.pod}
          </div>
        </div>
      )}

      <DemoSection />
    </div>
  );
}

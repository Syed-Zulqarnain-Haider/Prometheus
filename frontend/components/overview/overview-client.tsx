"use client";

import { Check, LayoutGrid, RotateCcw, X } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
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
import {
  useDashboardLayout,
  useResetDashboardLayout,
  useSaveDashboardLayout,
} from "@/lib/api-hooks";
import { defaultLayouts, normalizeLayouts, type OverviewItemId } from "@/lib/overview-layout";
import { useFilters } from "@/lib/use-filters";

const PAGE = "overview";

export function OverviewClient() {
  const { filters } = useFilters();
  const [editMode, setEditMode] = useState(false);

  const layoutQuery = useDashboardLayout(PAGE);
  const saveLayout = useSaveDashboardLayout(PAGE);
  const resetLayout = useResetDashboardLayout(PAGE);

  // This user's saved layout (reconciled with the current widget set), or the default
  // when nothing is saved. Applied to BOTH view and edit mode so it persists after
  // exiting the editor and after re-login.
  const savedLayouts = useMemo<Layouts>(() => {
    const saved = layoutQuery.data?.layout;
    return saved ? normalizeLayouts(saved) : defaultLayouts();
  }, [layoutQuery.data]);

  // Working copy: edited in place while customizing; reseeded when the saved layout
  // changes (initial load, after save, after reset).
  const [layouts, setLayouts] = useState<Layouts>(savedLayouts);
  useEffect(() => {
    setLayouts(savedLayouts);
  }, [savedLayouts]);

  // The EXISTING widgets, wrapped untouched — each keeps its own data fetching, filter
  // reactivity, loading/empty/error states and RBAC. The KPI row is a FIXED full-width
  // header (below) and is intentionally NOT part of the draggable grid.
  const items: Record<OverviewItemId, ReactNode> = {
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

  function handleSave() {
    saveLayout.mutate(layouts);
    setEditMode(false);
  }

  function handleCancel() {
    setLayouts(savedLayouts); // discard unsaved drags
    setEditMode(false);
  }

  function handleReset() {
    resetLayout.mutate(); // clears the saved layout server-side
    setLayouts(defaultLayouts()); // restore the default arrangement immediately
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader title="Executive Overview" />
        <div className="flex items-center gap-2">
          {editMode ? (
            <>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={handleReset}
                disabled={resetLayout.isPending}
              >
                <RotateCcw className="h-4 w-4" />
                Reset to default
              </Button>
              <Button variant="ghost" size="sm" className="gap-2" onClick={handleCancel}>
                <X className="h-4 w-4" />
                Cancel
              </Button>
              <Button
                variant="default"
                size="sm"
                className="gap-2"
                onClick={handleSave}
                disabled={saveLayout.isPending}
              >
                <Check className="h-4 w-4" />
                {saveLayout.isPending ? "Saving…" : "Save"}
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => setEditMode(true)}
            >
              <LayoutGrid className="h-4 w-4" />
              Customize layout
            </Button>
          )}
        </div>
      </div>

      {/* Fixed full-width KPI header — never draggable, never clipped. */}
      <KpiRow filters={filters} />

      {/* Everything below the KPIs is the draggable/resizable grid. In view mode it is
          static but still laid out by the saved positions, so the arrangement persists
          outside the editor. Stacks to a single column below the lg breakpoint. */}
      <DashboardGrid
        items={items}
        layouts={layouts}
        editable={editMode}
        onLayoutsChange={setLayouts}
      />

      <DemoSection />
    </div>
  );
}

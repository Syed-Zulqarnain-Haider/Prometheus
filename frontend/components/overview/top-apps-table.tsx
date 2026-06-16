"use client";

import { RevenueTable } from "@/components/overview/revenue-table";
import type { Filters } from "@/lib/filters";

/** Top Apps by Revenue — one row per game (with its publisher), sorted by Gross Rev. */
export function TopAppsTable({ filters }: { filters: Filters }) {
  return <RevenueTable title="Top Apps by Revenue" filters={filters} />;
}

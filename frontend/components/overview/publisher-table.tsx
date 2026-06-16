"use client";

import { RevenueTable } from "@/components/overview/revenue-table";
import type { Filters } from "@/lib/filters";

/** Publisher Performance — one row per (publisher, game). Each game maps to a single
 *  publisher, so this is the per-game table led by the Publisher column. */
export function PublisherTable({ filters }: { filters: Filters }) {
  return <RevenueTable title="Publisher Performance" filters={filters} />;
}

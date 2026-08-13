"use client";

import { RevenueTable } from "@/components/overview/revenue-table";
import type { Filters } from "@/lib/filters";

/** HOU Performance - one row per (HOU, game): the per-game table led by the HOU that
 *  owns it, which is how the owner reads this board. */
export function PublisherTable({ filters }: { filters: Filters }) {
  return <RevenueTable title="HOU Performance" filters={filters} />;
}

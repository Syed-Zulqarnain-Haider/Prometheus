"use client";

import { Suspense } from "react";

import { AppsExplorer } from "@/components/apps/apps-explorer";
import { Skeleton } from "@/components/ui/skeleton";
import { useFilters } from "@/lib/use-filters";

function AppsExplorerWithFilters() {
  const { filters } = useFilters();
  return <AppsExplorer filters={filters} />;
}

export default function AppsExplorerPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <AppsExplorerWithFilters />
    </Suspense>
  );
}

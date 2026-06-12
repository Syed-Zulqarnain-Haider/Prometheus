import { Suspense } from "react";

import { OverviewClient } from "@/components/overview/overview-client";
import { Skeleton } from "@/components/ui/skeleton";

export default function OverviewPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <OverviewClient />
    </Suspense>
  );
}

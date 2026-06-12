import { Suspense } from "react";

import { RevenueClient } from "@/components/revenue/revenue-client";
import { Skeleton } from "@/components/ui/skeleton";

export default function RevenuePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <RevenueClient />
    </Suspense>
  );
}

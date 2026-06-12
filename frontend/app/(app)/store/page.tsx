import { Suspense } from "react";

import { StoreClient } from "@/components/store/store-client";
import { Skeleton } from "@/components/ui/skeleton";

export default function StorePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <StoreClient />
    </Suspense>
  );
}

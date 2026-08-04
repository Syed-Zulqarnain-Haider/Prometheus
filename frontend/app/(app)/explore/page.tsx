import { Suspense } from "react";

import { ExploreClient } from "@/components/explore/explore-client";
import { Skeleton } from "@/components/ui/skeleton";

export default function ExplorePage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <ExploreClient />
    </Suspense>
  );
}

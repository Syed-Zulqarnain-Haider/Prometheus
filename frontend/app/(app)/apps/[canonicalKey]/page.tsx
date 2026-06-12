import { Suspense } from "react";

import { AppDetailClient } from "@/components/app-detail/app-detail-client";
import { Skeleton } from "@/components/ui/skeleton";

export default function AppDetailPage({
  params,
}: {
  params: { canonicalKey: string };
}) {
  const canonicalKey = decodeURIComponent(params.canonicalKey);
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <AppDetailClient canonicalKey={canonicalKey} />
    </Suspense>
  );
}

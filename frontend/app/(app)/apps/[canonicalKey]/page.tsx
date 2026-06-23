import { Suspense } from "react";

import { AppDetailClient } from "@/components/app-detail/app-detail-client";
import { Skeleton } from "@/components/ui/skeleton";

// Next 15+: dynamic route `params` is async (a Promise) and must be awaited.
export default async function AppDetailPage({
  params,
}: {
  params: Promise<{ canonicalKey: string }>;
}) {
  const { canonicalKey } = await params;
  const decoded = decodeURIComponent(canonicalKey);
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <AppDetailClient canonicalKey={decoded} />
    </Suspense>
  );
}

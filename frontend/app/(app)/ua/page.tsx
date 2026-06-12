import { Suspense } from "react";

import { UaClient } from "@/components/ua/ua-client";
import { Skeleton } from "@/components/ui/skeleton";

export default function UaPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <UaClient />
    </Suspense>
  );
}

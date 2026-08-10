import { Suspense } from "react";

import { CompareClient } from "@/components/compare/compare-client";
import { PageHeader } from "@/components/layout/page-header";

export default function ComparePage() {
  return (
    <div>
      <PageHeader
        title="Compare"
        description="Two periods side by side, under the same dimension filters. Period B follows Period A (previous period or last year) until you pin a custom range."
      />
      {/* CompareClient reads the URL-synced filters (useSearchParams), so it must render
          inside a Suspense boundary for the static prerender pass. */}
      <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
        <CompareClient />
      </Suspense>
    </div>
  );
}

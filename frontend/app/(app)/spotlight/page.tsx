import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { SpotlightClient } from "@/components/spotlight/spotlight-client";

export const metadata: Metadata = { title: "Spotlight - Prometheus" };

export default function SpotlightPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="App Spotlight"
        description="Every app in app_master_v2, shaded by completeness - red where publisher, HOU, pod, pod owner, partner name or net revenue share is missing, green where the record is filled. Click a tile to edit it."
      />
      <Suspense>
        <SpotlightClient />
      </Suspense>
    </div>
  );
}

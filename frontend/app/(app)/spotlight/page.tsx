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
        description="Apps in app_master_v2 missing publisher, HOU, pod, pod owner, partner name or net revenue share. Fill them in here."
      />
      <Suspense>
        <SpotlightClient />
      </Suspense>
    </div>
  );
}

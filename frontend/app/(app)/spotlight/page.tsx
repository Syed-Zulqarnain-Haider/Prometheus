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
        description="One app at a time: revenue, installs and UA cost. Swipe through the deck."
      />
      <Suspense>
        <SpotlightClient />
      </Suspense>
    </div>
  );
}

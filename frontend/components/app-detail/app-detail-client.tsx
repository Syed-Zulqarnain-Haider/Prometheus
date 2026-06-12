"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { AppTrend } from "@/components/app-detail/app-trend";
import { MetadataCard } from "@/components/app-detail/metadata-card";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { useAppDetail } from "@/lib/api-hooks";
import type { Filters } from "@/lib/filters";
import type { Platform } from "@/lib/types";
import { useFilters } from "@/lib/use-filters";

const PLATFORMS: { value: Platform | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "ios", label: "iOS" },
  { value: "android", label: "Android" },
];

const REVENUE_METRICS = [
  { key: "total_revenue_usd", label: "Revenue" },
  { key: "total_ad_revenue_usd", label: "Ad revenue" },
  { key: "total_iap_net_usd", label: "IAP net" },
];
const INSTALL_METRICS = [
  { key: "store_total_installs", label: "Total installs" },
  { key: "store_organic_installs", label: "Organic" },
  { key: "total_paid_installs", label: "Paid" },
];

export function AppDetailClient({ canonicalKey }: { canonicalKey: string }) {
  const { filters } = useFilters();
  const detail = useAppDetail(canonicalKey);
  const [platform, setPlatform] = useState<Platform | null>(filters.platform);

  const appFilters = useMemo<Filters>(
    () => ({ ...filters, apps: [canonicalKey], platform }),
    [filters, canonicalKey, platform],
  );

  if (detail.isError) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <h1 className="text-xl font-semibold">
          {notFound ? "App not found" : "Couldn't load this app"}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {notFound
            ? "It may not exist, or it's outside your access scope."
            : "Please try again."}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href="/apps">← Back to Apps Explorer</Link>
        </Button>
      </div>
    );
  }

  const title = detail.data?.app_name ?? canonicalKey;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/apps" className="text-xs text-muted-foreground hover:underline">
            ← Apps Explorer
          </Link>
          <PageHeader title={title} />
        </div>
        <div className="flex items-center gap-1">
          {PLATFORMS.map((p) => (
            <Button
              key={p.label}
              size="sm"
              variant={platform === p.value ? "default" : "outline"}
              onClick={() => setPlatform(p.value)}
            >
              {p.label}
            </Button>
          ))}
        </div>
      </div>

      {detail.isLoading || !detail.data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <MetadataCard app={detail.data} />
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AppTrend title="Revenue" filters={appFilters} metrics={REVENUE_METRICS} unit="usd" />
        <AppTrend
          title="UA Spend"
          filters={appFilters}
          metrics={[{ key: "total_ua_spend_usd", label: "Spend" }]}
          unit="usd"
        />
        <AppTrend title="Installs" filters={appFilters} metrics={INSTALL_METRICS} unit="number" />
        <AppTrend
          title="Profit"
          filters={appFilters}
          metrics={[{ key: "profit_usd", label: "Profit" }]}
          unit="usd"
        />
      </div>
    </div>
  );
}

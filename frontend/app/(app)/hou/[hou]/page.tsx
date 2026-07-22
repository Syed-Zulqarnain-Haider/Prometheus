"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { MonthlyTrend } from "@/components/overview/monthly-trend";
import { RevenueVsSpend } from "@/components/overview/revenue-vs-spend";
import { Card, CardContent } from "@/components/ui/card";
import { useApps, useSummary } from "@/lib/api-hooks";
import { useFilters } from "@/lib/use-filters";

function fmtUsd(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${Math.round(v).toLocaleString()}`;
}
function fmtCount(v: number | null | undefined): string {
  if (v == null) return "—";
  return Math.round(v).toLocaleString();
}
function n(v: number | null | undefined): number | null {
  return v == null ? null : v;
}

export default function HouDetailPage() {
  const params = useParams();
  const hou = decodeURIComponent(String(params.hou ?? ""));
  const { filters } = useFilters();

  // Inject the HOU as a (narrowing) filter — RBAC still applies server-side.
  const scoped = useMemo(() => ({ ...filters, hou: [hou] }), [filters, hou]);
  const summary = useSummary(scoped);
  const cur = summary.data?.current ?? {};

  // Apps assigned to this HOU (RBAC-scoped by the apps endpoint).
  const apps = useApps();
  const houApps = useMemo(
    () =>
      (apps.data?.apps ?? [])
        .filter((a) => (a.hou ?? "") === hou)
        .sort((x, y) => (x.app_name ?? x.canonical_key).localeCompare(y.app_name ?? y.canonical_key)),
    [apps.data, hou],
  );

  const grossRev =
    cur.total_iap_gross_usd == null && cur.total_ad_revenue_usd == null
      ? null
      : (cur.total_iap_gross_usd ?? 0) + (cur.total_ad_revenue_usd ?? 0);
  const netProfit =
    cur.profit_usd != null
      ? cur.profit_usd
      : cur.total_revenue_usd == null
        ? null
        : (cur.total_revenue_usd ?? 0) - (cur.total_ua_spend_usd ?? 0);

  const tiles: { label: string; value: string }[] = [
    { label: "Gross Revenue", value: fmtUsd(grossRev) },
    { label: "Net Revenue", value: fmtUsd(n(cur.total_revenue_usd)) },
    { label: "Net Profit", value: fmtUsd(netProfit) },
    { label: "UA Cost", value: fmtUsd(n(cur.total_ua_spend_usd)) },
    { label: "Total Installs", value: fmtCount(n(cur.store_total_installs)) },
    { label: "Organic Installs", value: fmtCount(n(cur.store_organic_installs)) },
    { label: "Ad Revenue", value: fmtUsd(n(cur.total_ad_revenue_usd)) },
    { label: "IAP Revenue", value: fmtUsd(n(cur.total_iap_net_usd)) },
  ];

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Overview
        </Link>
        <h1 className="font-display text-2xl">
          HOU — <span className="text-[color:var(--color-accent)]">{hou}</span>
        </h1>
        <p className="text-sm text-muted-foreground">
          Analytics for this HOU across the selected date range. Respects your access scope.
        </p>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {tiles.map((t) => (
          <Card key={t.label}>
            <CardContent className="py-4">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">{t.label}</p>
              <p className="mt-1 font-display text-2xl leading-none tabular-nums">
                {summary.isLoading ? "…" : t.value}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Trend + revenue-vs-spend, reused with the HOU-scoped filters */}
      <div className="grid gap-4 lg:grid-cols-2">
        <MonthlyTrend filters={scoped} />
        <RevenueVsSpend filters={scoped} />
      </div>

      {/* Apps assigned to this HOU */}
      <Card>
        <CardContent className="py-4">
          <p className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">
            Apps in this HOU ({houApps.length})
          </p>
          {apps.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : houApps.length === 0 ? (
            <p className="text-sm text-muted-foreground">No apps assigned to this HOU.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {houApps.map((a) => (
                <Link
                  key={a.canonical_key}
                  href={`/apps/${encodeURIComponent(a.canonical_key)}`}
                  className="rounded-full border px-3 py-1 text-sm hover:bg-accent"
                >
                  {a.app_name ?? a.canonical_key}
                  {a.publisher && (
                    <span className="ml-1 text-xs text-muted-foreground">{a.publisher}</span>
                  )}
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

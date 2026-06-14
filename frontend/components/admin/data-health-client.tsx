"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataHealth, useMe } from "@/lib/api-hooks";
import { formatDateTime, formatNumber } from "@/lib/format";

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge variant="outline">unknown</Badge>;
  const variant =
    status === "success" ? "secondary" : status === "running" ? "outline" : "destructive";
  return <Badge variant={variant}>{status}</Badge>;
}

export function DataHealthClient() {
  const { data: me, isLoading: meLoading } = useMe();
  const { data, isLoading } = useDataHealth();

  if (meLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!me?.capabilities.includes("admin_panel")) {
    return (
      <p className="text-sm text-muted-foreground">
        You don&apos;t have access to the data-health view.
      </p>
    );
  }
  if (isLoading || !data) {
    return <p className="text-sm text-muted-foreground">Loading data health…</p>;
  }

  return (
    <div className="space-y-4">
      {/* Warnings / all-clear */}
      {data.warnings.length > 0 ? (
        <Card className="border-destructive/50">
          <CardContent className="space-y-1 py-3">
            {data.warnings.map((warning, index) => (
              <div key={index} className="flex items-start gap-2 text-sm text-destructive">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{warning}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
            <CheckCircle2 className="h-4 w-4 text-primary" />
            Pipeline healthy — data is current.
          </CardContent>
        </Card>
      )}

      {/* Freshness summary */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Data as of</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">
            {formatDateTime(data.bq_built_at)}
            {data.is_stale && <Badge variant="destructive" className="ml-2">stale</Badge>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Last run</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">
            <StatusBadge status={data.last_status} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Rows loaded</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">
            {formatNumber(data.rows_loaded)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Unmapped apps</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">
            {formatNumber(data.unmapped_count)}
          </CardContent>
        </Card>
      </div>

      {/* Recent runs */}
      <Card>
        <CardHeader>
          <CardTitle>Recent sync runs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Started</th>
                  <th className="px-3 py-2">Finished</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Rows</th>
                  <th className="px-3 py-2">Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_runs.map((run) => (
                  <tr key={run.id} className="border-t align-top">
                    <td className="whitespace-nowrap px-3 py-1.5">
                      {formatDateTime(run.started_at)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5">
                      {formatDateTime(run.finished_at)}
                    </td>
                    <td className="px-3 py-1.5">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {formatNumber(run.rows_loaded)}
                    </td>
                    <td className="max-w-xs truncate px-3 py-1.5 text-muted-foreground">
                      {run.error_detail ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Unmapped apps */}
      {data.unmapped_apps.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Unmapped apps ({data.unmapped_count})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Canonical key</th>
                    <th className="px-3 py-2">App name</th>
                    <th className="px-3 py-2">Publisher</th>
                    <th className="px-3 py-2">Platform key</th>
                  </tr>
                </thead>
                <tbody>
                  {data.unmapped_apps.map((app) => (
                    <tr key={app.canonical_key} className="border-t">
                      <td className="px-3 py-1.5 font-mono text-xs">{app.canonical_key}</td>
                      <td className="px-3 py-1.5">{app.app_name ?? "—"}</td>
                      <td className="px-3 py-1.5">{app.publisher ?? "—"}</td>
                      <td className="px-3 py-1.5">{app.platform_keys ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

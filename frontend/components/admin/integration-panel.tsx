"use client";

import { Activity, Database, Plug, RefreshCw, Server } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api-client";
import {
  type AppSetting,
  type ConnectionStatus,
  useAppSettings,
  useIntegrationStatus,
  useTestBigQuery,
  useUpdateSetting,
} from "@/lib/api-hooks";
import { formatDateTime, formatNumber } from "@/lib/format";

function StatusBadge({ status }: { status: ConnectionStatus["status"] }) {
  if (status === "up") return <Badge variant="secondary">connected</Badge>;
  if (status === "not_configured") return <Badge variant="outline">not configured</Badge>;
  return <Badge variant="destructive">down</Badge>;
}

function SyncStatusBadge({ status }: { status: string }) {
  const variant =
    status === "success" ? "secondary" : status === "running" ? "outline" : "destructive";
  return <Badge variant={variant}>{status}</Badge>;
}

const ICONS = { bigquery: Activity, postgres: Database, redis: Server } as const;

function HealthCard({ id, status }: { id: keyof typeof ICONS; status: ConnectionStatus }) {
  const Icon = ICONS[id];
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {status.name}
        </CardTitle>
        <StatusBadge status={status.status} />
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        {status.latency_ms != null ? (
          <span className="tabular-nums">{status.latency_ms} ms</span>
        ) : (
          <span>{status.detail ?? "—"}</span>
        )}
      </CardContent>
    </Card>
  );
}

/** A single editable string setting (e.g. GCP project, BigQuery view, sync time/tz). */
function StrSetting({ setting }: { setting: AppSetting }) {
  const update = useUpdateSetting();
  const initial = String(setting.value);
  const [value, setValue] = useState(initial);
  const dirty = value !== initial;
  const inputType = setting.key === "sync_schedule_time" ? "time" : "text";
  const placeholder =
    setting.key === "gcp_project" ? "(uses the reader key's own project)" : undefined;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{setting.label}</p>
        <p className="text-xs text-muted-foreground">{setting.description}</p>
      </div>
      <div className="flex flex-col items-end gap-1">
        <div className="flex items-center gap-2">
          <Input
            type={inputType}
            className="w-64"
            value={value}
            placeholder={placeholder}
            onChange={(e) => setValue(e.target.value)}
          />
          <Button
            size="sm"
            disabled={!dirty || update.isPending}
            onClick={() => update.mutate({ key: setting.key, value })}
          >
            Save
          </Button>
        </div>
        {update.isError && (
          <p className="text-xs text-destructive">
            {update.error instanceof ApiError ? update.error.message : "Update failed."}
          </p>
        )}
      </div>
    </div>
  );
}

/** A single boolean (toggle) setting (e.g. daily sync enabled). */
function BoolSetting({ setting }: { setting: AppSetting }) {
  const update = useUpdateSetting();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{setting.label}</p>
        <p className="text-xs text-muted-foreground">{setting.description}</p>
      </div>
      <Checkbox
        checked={Boolean(setting.value)}
        disabled={update.isPending}
        onCheckedChange={(checked) =>
          update.mutate({ key: setting.key, value: checked === true })
        }
      />
    </div>
  );
}

export function IntegrationPanel() {
  const status = useIntegrationStatus();
  const settings = useAppSettings();
  const testBq = useTestBigQuery();

  const integrationSettings = (settings.data ?? []).filter((s) => s.group === "integration");

  return (
    <div className="space-y-6">
      {/* A) Connection health */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Connection health
        </h2>
        {status.isLoading || !status.data ? (
          <p className="text-sm text-muted-foreground">Checking connections…</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">
            <HealthCard id="bigquery" status={status.data.bigquery} />
            <HealthCard id="postgres" status={status.data.postgres} />
            <HealthCard id="redis" status={status.data.redis} />
          </div>
        )}
      </section>

      {/* B) BigQuery test connection */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          BigQuery access
        </h2>
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <p className="text-sm text-muted-foreground">
              Run a lightweight, read-only check against BigQuery using the mounted reader
              key. It never modifies anything and never reveals credentials.
            </p>
            <Button
              className="gap-2"
              disabled={testBq.isPending}
              onClick={() => testBq.mutate()}
            >
              {testBq.isPending ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Plug className="h-4 w-4" />
              )}
              Test connection
            </Button>
          </CardContent>
          {testBq.data && (
            <CardContent className="pt-0">
              <p className={`text-sm ${testBq.data.ok ? "text-primary" : "text-destructive"}`}>
                {testBq.data.message}
              </p>
            </CardContent>
          )}
        </Card>
      </section>

      {/* C) Integration settings (non-secret config) */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Sync configuration
        </h2>
        <Card>
          <CardContent className="divide-y py-0">
            {settings.isLoading ? (
              <p className="py-4 text-sm text-muted-foreground">Loading settings…</p>
            ) : integrationSettings.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">No integration settings.</p>
            ) : (
              integrationSettings.map((setting) =>
                setting.type === "bool" ? (
                  <BoolSetting key={setting.key} setting={setting} />
                ) : (
                  <StrSetting key={setting.key} setting={setting} />
                ),
              )
            )}
          </CardContent>
        </Card>
        <p className="text-xs text-muted-foreground">
          These are non-secret operational parameters only. The BigQuery service-account key
          is a file mounted on the server — it is never uploaded, stored, or shown here.
        </p>
      </section>

      {/* D) Sync history */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Sync history
        </h2>
        <Card>
          <CardHeader>
            <CardTitle>Recent sync runs</CardTitle>
          </CardHeader>
          <CardContent>
            {status.isLoading || !status.data ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : status.data.recent_syncs.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No sync has run yet. History appears here after the first sync.
              </p>
            ) : (
              <div className="overflow-auto rounded-md border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Started</th>
                      <th className="px-3 py-2">Finished</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2 text-right">Rows</th>
                      <th className="px-3 py-2">Data as of</th>
                      <th className="px-3 py-2">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.data.recent_syncs.map((run) => (
                      <tr key={run.id} className="border-t align-top">
                        <td className="whitespace-nowrap px-3 py-1.5">
                          {formatDateTime(run.started_at)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5">
                          {formatDateTime(run.finished_at)}
                        </td>
                        <td className="px-3 py-1.5">
                          <SyncStatusBadge status={run.status} />
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">
                          {formatNumber(run.rows_loaded)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-1.5">
                          {formatDateTime(run.bq_built_at)}
                        </td>
                        <td className="max-w-xs truncate px-3 py-1.5 text-muted-foreground">
                          {run.error_detail ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

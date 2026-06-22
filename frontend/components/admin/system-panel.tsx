"use client";

import { Activity, Database, Play, RefreshCw, Server } from "lucide-react";
import { useState } from "react";

import { DataHealthClient } from "@/components/admin/data-health-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  type AppSetting,
  type ConnectionStatus,
  type SyncTriggerResult,
  useAppSettings,
  useRunSync,
  useSystemHealth,
  useUpdateSetting,
} from "@/lib/api-hooks";

function StatusBadge({ status }: { status: ConnectionStatus["status"] }) {
  if (status === "up") return <Badge variant="secondary">connected</Badge>;
  if (status === "not_configured") return <Badge variant="outline">not configured</Badge>;
  return <Badge variant="destructive">down</Badge>;
}

const ICONS = { postgres: Database, redis: Server, bigquery: Activity } as const;

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

/** A single editable integer setting (e.g. the freshness threshold). */
function IntSetting({ setting }: { setting: AppSetting }) {
  const update = useUpdateSetting();
  const [value, setValue] = useState(String(setting.value));
  const dirty = value !== String(setting.value);
  const num = Number(value);
  const valid =
    value.trim() !== "" &&
    Number.isInteger(num) &&
    (setting.minimum == null || num >= setting.minimum) &&
    (setting.maximum == null || num <= setting.maximum);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{setting.label}</p>
        <p className="text-xs text-muted-foreground">{setting.description}</p>
      </div>
      <div className="flex items-center gap-2">
        <Input
          type="number"
          className="w-28"
          value={value}
          min={setting.minimum ?? undefined}
          max={setting.maximum ?? undefined}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button
          size="sm"
          disabled={!dirty || !valid || update.isPending}
          onClick={() => update.mutate({ key: setting.key, value: num })}
        >
          Save
        </Button>
      </div>
    </div>
  );
}

/** A single boolean (toggle) setting (e.g. show demo widgets). */
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

export function SystemPanel() {
  const health = useSystemHealth();
  const settings = useAppSettings();
  const runSync = useRunSync();
  const [syncResult, setSyncResult] = useState<SyncTriggerResult | null>(null);

  return (
    <div className="space-y-6">
      {/* A) Connection health */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Connection health
        </h2>
        {health.isLoading || !health.data ? (
          <p className="text-sm text-muted-foreground">Checking connections…</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">
            <HealthCard id="postgres" status={health.data.postgres} />
            <HealthCard id="redis" status={health.data.redis} />
            <HealthCard id="bigquery" status={health.data.bigquery} />
          </div>
        )}
      </section>

      {/* C) Run sync now */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Data sync
        </h2>
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <p className="text-sm text-muted-foreground">
              Trigger the data sync on demand. Requires a configured data source.
            </p>
            <Button
              className="gap-2"
              disabled={runSync.isPending}
              onClick={() => runSync.mutate(undefined, { onSuccess: setSyncResult })}
            >
              {runSync.isPending ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Run sync now
            </Button>
          </CardContent>
          {syncResult && (
            <CardContent className="pt-0">
              <p
                className={`text-sm ${
                  syncResult.triggered ? "text-primary" : "text-muted-foreground"
                }`}
              >
                {syncResult.message}
              </p>
            </CardContent>
          )}
        </Card>
      </section>

      {/* B) Operational settings */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Operational settings
        </h2>
        <Card>
          <CardContent className="divide-y py-0">
            {settings.isLoading || !settings.data ? (
              <p className="py-4 text-sm text-muted-foreground">Loading settings…</p>
            ) : (
              settings.data.map((setting) =>
                setting.type === "bool" ? (
                  <BoolSetting key={setting.key} setting={setting} />
                ) : (
                  <IntSetting key={setting.key} setting={setting} />
                ),
              )
            )}
          </CardContent>
        </Card>
        <p className="text-xs text-muted-foreground">
          Only non-secret operational settings are shown here. Credentials and connection
          strings are never stored in the database or displayed — they live in the
          environment / Secret Manager.
        </p>
      </section>

      {/* A) Sync / data health (reuses the existing Data Health view) */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Sync &amp; data health
        </h2>
        <DataHealthClient />
      </section>
    </div>
  );
}

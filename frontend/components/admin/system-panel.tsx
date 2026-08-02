"use client";

import { Activity, BellRing, Database, Play, RefreshCw, Server } from "lucide-react";
import { useState } from "react";

import { DataHealthClient } from "@/components/admin/data-health-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  type AlertsEvaluateResult,
  type AppSetting,
  type ConnectionStatus,
  type DigestResult,
  type SyncTriggerResult,
  useAppSettings,
  useEvaluateAlerts,
  useRunSync,
  useSendDigest,
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
          <span>{status.detail ?? ""}</span>
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
  const evalAlerts = useEvaluateAlerts();
  const [alertsResult, setAlertsResult] = useState<AlertsEvaluateResult | null>(null);
  const sendDigest = useSendDigest();
  const [digestResult, setDigestResult] = useState<DigestResult | null>(null);

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
              onClick={() => runSync.mutate({}, { onSuccess: setSyncResult })}
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
                  syncResult.triggered ? "text-positive" : "text-muted-foreground"
                }`}
              >
                {syncResult.message}
              </p>
            </CardContent>
          )}
        </Card>
      </section>

      {/* C2) Evaluate alerts now */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Proactive alerts
        </h2>
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <p className="text-sm text-muted-foreground">
              Run the anomaly checks now (revenue drop, spend spike, low ROAS, stale data). They
              also run automatically each day after the sync when &quot;Proactive alerts&quot; is
              enabled in the settings below.
            </p>
            <Button
              variant="outline"
              className="gap-2"
              disabled={evalAlerts.isPending}
              onClick={() => evalAlerts.mutate(undefined, { onSuccess: setAlertsResult })}
            >
              {evalAlerts.isPending ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <BellRing className="h-4 w-4" />
              )}
              Evaluate alerts now
            </Button>
          </CardContent>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 border-t py-4">
            <p className="text-sm text-muted-foreground">
              Send the daily performance digest now. It also sends automatically each day when
              &quot;Daily digest email&quot; is enabled below.
            </p>
            <Button
              variant="outline"
              className="gap-2"
              disabled={sendDigest.isPending}
              onClick={() => sendDigest.mutate(undefined, { onSuccess: setDigestResult })}
            >
              {sendDigest.isPending ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <BellRing className="h-4 w-4" />
              )}
              Send digest now
            </Button>
          </CardContent>
          {digestResult && (
            <CardContent className="pt-0 text-sm">
              {digestResult.sent && digestResult.preview ? (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                  {digestResult.preview}
                </pre>
              ) : (
                <p className="text-muted-foreground">
                  Digest is disabled or there&apos;s no data yet — nothing sent.
                </p>
              )}
            </CardContent>
          )}
          {alertsResult && (
            <CardContent className="pt-0 text-sm">
              {alertsResult.count === 0 ? (
                <p className="text-positive">No alerts — everything within thresholds.</p>
              ) : (
                <ul className="space-y-1">
                  {alertsResult.fired.map((a) => (
                    <li key={a.key} className="text-muted-foreground">
                      <span
                        className={
                          a.severity === "critical" ? "text-destructive" : "text-[color:var(--color-amber)]"
                        }
                      >
                        ●
                      </span>{" "}
                      <span className="font-medium text-foreground">{a.title}</span> — {a.body}
                    </li>
                  ))}
                </ul>
              )}
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

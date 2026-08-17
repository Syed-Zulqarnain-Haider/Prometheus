"use client";

import { Mail, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

/* Mail (SMTP) settings, editable in place.
 *
 * The password field is WRITE-ONLY end to end: the API's response object has no password
 * field at all, so this form cannot display one even by mistake. The input is therefore
 * always empty on load; "Stored" beside it means one is saved. Leaving it empty on save
 *  keeps the stored one; typing replaces it; ticking "clear" removes it.
 *
 * "Send test email" goes to the CALLER'S OWN address by design - proving the settings
 * work never requires the ability to mail arbitrary recipients. */

interface SmtpConfig {
  host: string | null;
  port: number;
  username: string | null;
  from_address: string | null;
  use_tls: boolean;
  password_set: boolean;
  updated_at: string | null;
  encryption_available: boolean;
  configured: boolean;
}

interface SmtpTestResult {
  ok: boolean;
  detail: string;
}

function useSmtpConfig() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["smtp-config"],
    queryFn: () => apiFetch<SmtpConfig>("/api/v1/admin/smtp"),
    enabled: Boolean(user),
  });
}

export function SmtpPanel() {
  const queryClient = useQueryClient();
  const config = useSmtpConfig();

  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [username, setUsername] = useState("");
  const [fromAddress, setFromAddress] = useState("");
  const [useTls, setUseTls] = useState(true);
  const [password, setPassword] = useState("");
  const [clearPassword, setClearPassword] = useState(false);
  const [seeded, setSeeded] = useState(false);

  // Seed the form ONCE from the server. Re-seeding on every refetch would wipe an
  // admin's half-typed edits each time the query refreshes in the background.
  useEffect(() => {
    if (seeded || !config.data) return;
    setHost(config.data.host ?? "");
    setPort(String(config.data.port));
    setUsername(config.data.username ?? "");
    setFromAddress(config.data.from_address ?? "");
    setUseTls(config.data.use_tls);
    setSeeded(true);
  }, [config.data, seeded]);

  const save = useMutation({
    mutationFn: () =>
      apiFetch<SmtpConfig>("/api/v1/admin/smtp", {
        method: "PUT",
        body: JSON.stringify({
          host: host.trim() || null,
          port: Number(port),
          username: username.trim() || null,
          from_address: fromAddress.trim() || null,
          use_tls: useTls,
          // Three-valued: omitted = keep, "" = clear, text = replace.
          ...(clearPassword ? { password: "" } : password ? { password } : {}),
        }),
      }),
    onSuccess: () => {
      setPassword("");
      setClearPassword(false);
      void queryClient.invalidateQueries({ queryKey: ["smtp-config"] });
    },
  });

  const test = useMutation({
    mutationFn: () =>
      apiFetch<SmtpTestResult>("/api/v1/admin/smtp/test", { method: "POST" }),
  });

  const portNum = Number(port);
  const portValid = Number.isInteger(portNum) && portNum >= 1 && portNum <= 65535;

  if (config.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading mail settings...</p>;
  }
  if (config.isError) {
    return (
      <p className="text-sm text-destructive">
        Could not load mail settings: {(config.error as Error).message}
      </p>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-muted-foreground" />
          Email (SMTP)
        </CardTitle>
        {config.data?.configured ? (
          <Badge variant="secondary">configured</Badge>
        ) : (
          <Badge variant="outline">not configured</Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Host</span>
            <Input
              value={host}
              onChange={(event) => setHost(event.target.value)}
              placeholder="smtp.example.com"
              autoComplete="off"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Port</span>
            <Input
              type="number"
              value={port}
              onChange={(event) => setPort(event.target.value)}
              min={1}
              max={65535}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Username</span>
            <Input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="mailer@example.com"
              autoComplete="off"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs font-medium text-muted-foreground">From address</span>
            <Input
              type="email"
              value={fromAddress}
              onChange={(event) => setFromAddress(event.target.value)}
              placeholder="prometheus@example.com"
              autoComplete="off"
            />
          </label>
          <label className="space-y-1 text-sm sm:col-span-2">
            <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              Password
              {config.data?.password_set && <Badge variant="secondary">stored</Badge>}
            </span>
            <Input
              type="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                if (event.target.value) setClearPassword(false);
              }}
              placeholder={
                config.data?.password_set
                  ? "Leave empty to keep the stored password"
                  : "No password stored"
              }
              autoComplete="new-password"
              disabled={clearPassword}
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={useTls} onCheckedChange={(v) => setUseTls(v === true)} />
            Use TLS (STARTTLS)
          </label>
          {config.data?.password_set && (
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <Checkbox
                checked={clearPassword}
                onCheckedChange={(v) => {
                  setClearPassword(v === true);
                  if (v === true) setPassword("");
                }}
              />
              Clear the stored password
            </label>
          )}
        </div>

        {!config.data?.encryption_available && (
          <p className="text-xs text-[color:var(--color-amber)]">
            SMTP_SECRET_KEY is not set on the server, so a password cannot be stored from
            here. Every other field still saves; the password keeps coming from the
            environment.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            disabled={save.isPending || !portValid}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving..." : "Save mail settings"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={test.isPending || !config.data?.configured}
            onClick={() => test.mutate()}
          >
            <Send className="h-3.5 w-3.5" />
            {test.isPending ? "Sending..." : "Send test email"}
          </Button>
          <span className="text-xs text-muted-foreground">
            The test goes to your own address.
          </span>
        </div>

        {save.isError && (
          <p className="text-xs text-destructive">
            Could not save: {(save.error as Error).message}
          </p>
        )}
        {test.data && (
          <p
            className={
              test.data.ok ? "text-xs text-positive" : "text-xs text-destructive"
            }
          >
            {test.data.detail}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

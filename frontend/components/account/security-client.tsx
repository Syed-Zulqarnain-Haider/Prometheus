"use client";

import { LogOut, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRevokeSessions, useSecurity } from "@/lib/api-hooks";
import { useAuth } from "@/lib/auth-context";
import { formatDateTime } from "@/lib/format";

function deviceLabel(ua: string | null): string {
  if (!ua) return "Unknown device";
  // A light, dependency-free summary of the user agent.
  // Check iOS/iPadOS BEFORE macOS: iPadOS 13+ reports a "Macintosh" UA.
  const os = /Windows/.test(ua)
    ? "Windows"
    : /iPhone|iPad|iPod|iOS/.test(ua)
      ? "iOS/iPadOS"
      : /Android/.test(ua)
        ? "Android"
        : /Mac OS X|Macintosh/.test(ua)
          ? "macOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "Unknown OS";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Firefox\//.test(ua)
        ? "Firefox"
        : /Safari\//.test(ua)
          ? "Safari"
          : "Browser";
  return `${browser} on ${os}`;
}

export function SecurityClient() {
  const security = useSecurity();
  const revoke = useRevokeSessions();
  const { signOut } = useAuth();
  const [confirming, setConfirming] = useState(false);

  async function doRevoke() {
    try {
      await revoke.mutateAsync();
    } catch {
      // Surfaced via revoke.isError below — do NOT sign out on failure (nothing was revoked).
      return;
    }
    // The current session is now invalid too — sign out locally and return to login.
    await signOut();
  }

  const twoFactor = security.data?.two_factor ?? false;

  return (
    <div className="space-y-6">
      <PageHeader title="Security" description="Your sign-in protection and active devices." />

      {/* Two-factor status */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="flex items-center gap-2">
            {twoFactor ? (
              <ShieldCheck className="h-4 w-4 text-[color:var(--color-positive)]" />
            ) : (
              <ShieldAlert className="h-4 w-4 text-[color:var(--color-amber)]" />
            )}
            Two-factor authentication
          </CardTitle>
          <Badge variant={twoFactor ? "secondary" : "outline"}>
            {twoFactor ? "Active on this sign-in" : "Not used"}
          </Badge>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {twoFactor
            ? "This session was verified with a second factor."
            : "This session signed in without a second factor. Enable 2FA on your Google/Firebase account for stronger protection."}
        </CardContent>
      </Card>

      {/* Recent devices / activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent activity</CardTitle>
        </CardHeader>
        <CardContent>
          {security.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (security.data?.devices.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">No recent activity recorded yet.</p>
          ) : (
            <ul className="divide-y">
              {security.data?.devices.map((d, i) => (
                <li key={i} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium">{deviceLabel(d.user_agent)}</p>
                    <p className="text-xs text-muted-foreground">
                      {d.ip_address ?? "unknown IP"} · {d.events} action(s)
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatDateTime(d.last_seen)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Sign out everywhere */}
      <Card>
        <CardHeader>
          <CardTitle>Sign out of all devices</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Immediately end every signed-in session, including this one. Use this if you think
            an account or device is compromised. You&apos;ll need to sign in again.
          </p>
          {security.data?.sessions_revoked_at && (
            <p className="text-xs text-muted-foreground">
              Last done: {formatDateTime(security.data.sessions_revoked_at)}
            </p>
          )}
          {!confirming ? (
            <Button variant="destructive" className="gap-2" onClick={() => setConfirming(true)}>
              <LogOut className="h-4 w-4" />
              Sign out everywhere
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <Button
                variant="destructive"
                onClick={doRevoke}
                disabled={revoke.isPending}
              >
                {revoke.isPending ? "Signing out…" : "Confirm — sign out everywhere"}
              </Button>
              <Button variant="outline" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
            </div>
          )}
          {revoke.isError && (
            <p className="text-sm text-destructive">
              Couldn&apos;t sign out everywhere — please try again. Your sessions were not changed.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

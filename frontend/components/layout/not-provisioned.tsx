"use client";

import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Shown when a user has authenticated with Firebase (e.g. via Google or
 *  email/password) but is NOT provisioned in our database — no role, no scope, no
 *  data. Authentication never implies authorization here, so we surface a friendly
 *  message instead of a blank or broken dashboard. */
export function NotProvisioned({
  inactive = false,
  onSignOut,
}: {
  inactive?: boolean;
  onSignOut: () => void;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md rounded-lg border bg-card p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent">
          <ShieldAlert className="h-6 w-6 text-muted-foreground" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">
          {inactive ? "Account inactive" : "Account not provisioned"}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {inactive
            ? "Your account has been deactivated. Contact an administrator to restore access."
            : "Your account isn't provisioned for this dashboard yet. Contact an administrator to be granted access."}
        </p>
        <Button variant="outline" className="mt-6" onClick={onSignOut}>
          Sign out
        </Button>
      </div>
    </main>
  );
}

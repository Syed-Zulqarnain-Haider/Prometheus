"use client";

import { Clock } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useRequestAccess } from "@/lib/api-hooks";

/** Shown when a user authenticated (e.g. via Google) but has NO provisioned account.
 *  Instead of a dead-end, we record a pending access request and tell them it's awaiting
 *  an administrator's approval. Authentication is never authorization here. */
export function AccessRequestPending({ onSignOut }: { onSignOut: () => void }) {
  const { mutate, isError } = useRequestAccess();

  // Record the request once on mount (idempotent server-side — repeat calls are harmless).
  useEffect(() => {
    mutate();
  }, [mutate]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md rounded-lg border bg-card p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent">
          <Clock className="h-6 w-6 text-muted-foreground" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Access requested</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {isError
            ? "We couldn't submit your access request just now. Please sign out and try again later."
            : "Your request is pending administrator approval. You'll be able to sign in and see your dashboard once an admin grants you access."}
        </p>
        <Button variant="outline" className="mt-6" onClick={onSignOut}>
          Sign out
        </Button>
      </div>
    </main>
  );
}

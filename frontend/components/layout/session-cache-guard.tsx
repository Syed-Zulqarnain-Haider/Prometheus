"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { useAuth } from "@/lib/auth-context";

/** Drops every cached query the moment the session changes hands.
 *
 *  The TanStack cache is a plain in-memory store and outlives sign-out. On a shared machine
 *  that means the next person to sign in sees the previous user's revenue, spend and app
 *  list rendered from cache before their own request returns — figures their RBAC scopes may
 *  not entitle them to. The server was never wrong; the browser was showing someone else's
 *  answer.
 *
 *  Keyed on the Firebase UID rather than a signed-in boolean, so a direct A→B account switch
 *  (no null in between) clears too. The first resolution after a page load is not a change —
 *  `previousUid` starts unset, so a normal load keeps its cache.
 */
export function SessionCacheGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const previousUid = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (loading) return; // Firebase hasn't resolved yet — absence of a user is not a sign-out
    const uid = user?.uid ?? null;
    if (previousUid.current !== undefined && previousUid.current !== uid) {
      queryClient.clear();
    }
    previousUid.current = uid;
  }, [user, loading, queryClient]);

  return <>{children}</>;
}

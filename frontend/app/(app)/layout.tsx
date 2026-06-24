"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";

import { AccessRequestPending } from "@/components/layout/access-request-pending";
import { FilterBar } from "@/components/filters/filter-bar";
import { FreshnessBanner } from "@/components/layout/freshness-banner";
import { Header } from "@/components/layout/header";
import { NotProvisioned } from "@/components/layout/not-provisioned";
import { Sidebar } from "@/components/layout/sidebar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api-client";
import { useMe } from "@/lib/api-hooks";
import { useAuth } from "@/lib/auth-context";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, signOut } = useAuth();
  const router = useRouter();
  // Provisioning gate: Firebase auth alone is NOT access. We resolve /auth/me, and
  // an authenticated-but-unprovisioned user (any provider, incl. Google) is rejected
  // server-side — we show a friendly screen instead of a broken dashboard.
  const me = useMe();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user || me.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Skeleton className="h-24 w-64" />
      </div>
    );
  }

  if (me.isError) {
    const httpStatus = me.error instanceof ApiError ? me.error.status : 0;
    // 403 = provisioned but deactivated/expired; 401 = no account → offer to request access.
    if (httpStatus === 403) {
      return <NotProvisioned inactive onSignOut={() => void signOut()} />;
    }
    if (httpStatus === 401) {
      return <AccessRequestPending onSignOut={() => void signOut()} />;
    }
    // Anything else (5xx / network) is a transient failure — don't mislabel it as
    // "not provisioned" or "inactive"; let the user retry.
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="w-full max-w-md rounded-lg border bg-card p-8 text-center shadow-sm">
          <h1 className="text-xl font-semibold tracking-tight">Couldn&apos;t load your account</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Something went wrong reaching the server. Please try again in a moment.
          </p>
          <div className="mt-6 flex justify-center gap-2">
            <Button onClick={() => void me.refetch()}>Retry</Button>
            <Button variant="outline" onClick={() => void signOut()}>
              Sign out
            </Button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <FreshnessBanner />
        <Suspense
          fallback={
            <div className="border-b bg-card px-4 py-2">
              <Skeleton className="h-8 w-full max-w-xl" />
            </div>
          }
        >
          <FilterBar />
        </Suspense>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}

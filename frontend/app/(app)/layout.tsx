"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";

import { FilterBar } from "@/components/filters/filter-bar";
import { FreshnessBanner } from "@/components/layout/freshness-banner";
import { Header } from "@/components/layout/header";
import { NotProvisioned } from "@/components/layout/not-provisioned";
import { Sidebar } from "@/components/layout/sidebar";
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
    // 403 = provisioned but deactivated; anything else (401 unprovisioned) = no account.
    const inactive = me.error instanceof ApiError && me.error.status === 403;
    return <NotProvisioned inactive={inactive} onSignOut={() => void signOut()} />;
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

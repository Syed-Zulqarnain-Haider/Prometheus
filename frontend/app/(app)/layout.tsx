"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";

import { FilterBar } from "@/components/filters/filter-bar";
import { FreshnessBanner } from "@/components/layout/freshness-banner";
import { Header } from "@/components/layout/header";
import { Sidebar } from "@/components/layout/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth-context";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Skeleton className="h-24 w-64" />
      </div>
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

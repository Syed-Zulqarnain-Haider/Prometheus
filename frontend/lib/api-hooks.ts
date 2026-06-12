"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { AppsResponse, Freshness } from "@/lib/types";

export function useFreshness() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["freshness"],
    queryFn: () => apiFetch<Freshness>("/api/v1/meta/freshness"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

export function useApps() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["apps"],
    queryFn: () => apiFetch<AppsResponse>("/api/v1/apps"),
    enabled: Boolean(user),
    staleTime: 30 * 60 * 1000,
  });
}

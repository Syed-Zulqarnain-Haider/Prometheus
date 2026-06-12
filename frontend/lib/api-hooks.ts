"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch, buildQuery } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { type Filters, filtersToApiQuery } from "@/lib/filters";
import type {
  AppDetail,
  AppsResponse,
  BreakdownResponse,
  Bucket,
  Freshness,
  SummaryResponse,
  TableResponse,
  TimeseriesResponse,
} from "@/lib/types";

const AGG_STALE = 60 * 1000;

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

export function useAppDetail(canonicalKey: string) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["app-detail", canonicalKey],
    queryFn: () =>
      apiFetch<AppDetail>(`/api/v1/apps/${encodeURIComponent(canonicalKey)}`),
    enabled: Boolean(user) && Boolean(canonicalKey),
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 404) && count < 1,
  });
}

export function useSummary(filters: Filters) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), compare: true };
  return useQuery({
    queryKey: ["summary", params],
    queryFn: () =>
      apiFetch<SummaryResponse>(`/api/v1/metrics/summary${buildQuery(params)}`),
    enabled: Boolean(user),
    staleTime: AGG_STALE,
  });
}

export function useTimeseries(filters: Filters, metrics: string[], bucket: Bucket) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), metrics, bucket };
  return useQuery({
    queryKey: ["timeseries", params],
    queryFn: () =>
      apiFetch<TimeseriesResponse>(`/api/v1/metrics/timeseries${buildQuery(params)}`),
    enabled: Boolean(user) && metrics.length > 0,
    staleTime: AGG_STALE,
  });
}

export function useBreakdown(filters: Filters, groupBy: string, metrics: string[]) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), group_by: groupBy, metrics };
  return useQuery({
    queryKey: ["breakdown", params],
    queryFn: () =>
      apiFetch<BreakdownResponse>(`/api/v1/metrics/breakdown${buildQuery(params)}`),
    enabled: Boolean(user) && metrics.length > 0,
    staleTime: AGG_STALE,
  });
}

/** Keyset-paginated table for the Apps Explorer (server-side sort + cursor). */
export function useTableInfinite(
  filters: Filters,
  sort: string,
  direction: "asc" | "desc",
  limit = 50,
) {
  const { user } = useAuth();
  const base = { ...filtersToApiQuery(filters), sort, direction, limit };
  return useInfiniteQuery({
    queryKey: ["table-infinite", base],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      apiFetch<TableResponse>(
        `/api/v1/metrics/table${buildQuery({ ...base, cursor: pageParam ?? undefined })}`,
      ),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: Boolean(user),
    staleTime: AGG_STALE,
  });
}

export function useTable(filters: Filters, sort: string, limit = 10) {
  const { user } = useAuth();
  const params = { ...filtersToApiQuery(filters), sort, direction: "desc", limit };
  return useQuery({
    queryKey: ["table", params],
    queryFn: () =>
      apiFetch<TableResponse>(`/api/v1/metrics/table${buildQuery(params)}`),
    enabled: Boolean(user),
    staleTime: AGG_STALE,
  });
}

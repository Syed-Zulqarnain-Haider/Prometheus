"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { Layouts as GridLayouts } from "react-grid-layout";

import { ApiError, apiFetch, buildQuery } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import { previousWindow } from "@/lib/compare";
import { type Filters, filtersToApiQuery } from "@/lib/filters";
import type {
  AdminUser,
  AppDetail,
  AppsResponse,
  AuditPage,
  BreakdownResponse,
  Bucket,
  DataHealth,
  DirectoryEntry,
  Freshness,
  ReportRunResult,
  RevenueTarget,
  RoleConfig,
  SavedReport,
  SavedView,
  ShareOut,
  SummaryResponse,
  SyncRunOut,
  TableResponse,
  TargetsResponse,
  TimeseriesResponse,
  UserContext,
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

/** Previous-period timeseries (date-shifted window), only fetched in Compare mode.
 *  Used for the dashed "ghost" overlays. */
export function usePreviousTimeseries(
  filters: Filters,
  metrics: string[],
  bucket: Bucket,
) {
  const { user } = useAuth();
  const prev = previousWindow(filters.dateFrom, filters.dateTo);
  const shifted = { ...filters, dateFrom: prev.from, dateTo: prev.to, compare: false };
  const params = { ...filtersToApiQuery(shifted), metrics, bucket };
  return useQuery({
    queryKey: ["timeseries-prev", params],
    queryFn: () =>
      apiFetch<TimeseriesResponse>(`/api/v1/metrics/timeseries${buildQuery(params)}`),
    enabled: Boolean(user) && metrics.length > 0 && filters.compare,
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

// ── Identity (RBAC context + share directory) ────────────────────────────────
export function useMe() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<UserContext>("/api/v1/auth/me"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

export function useDirectory() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["directory"],
    queryFn: () => apiFetch<DirectoryEntry[]>("/api/v1/auth/directory"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Saved views ──────────────────────────────────────────────────────────────
export interface SavedViewInput {
  name: string;
  page: string;
  filters: Record<string, unknown>;
}

export function useSavedViews() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["saved-views"],
    queryFn: () => apiFetch<SavedView[]>("/api/v1/views"),
    enabled: Boolean(user),
  });
}

export function useCreateView() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SavedViewInput) =>
      apiFetch<SavedView>("/api/v1/views", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-views"] }),
  });
}

export function useDeleteView() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/views/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-views"] }),
  });
}

// ── Dashboard layouts (per-user drag-and-drop persistence) ──────────────────────
export interface DashboardLayoutOut {
  page: string;
  layout: GridLayouts | null;
  updated_at: string | null;
}

/** Load THIS user's saved layout for a page (layout=null → use the default). */
export function useDashboardLayout(page: string) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["dashboard-layout", page],
    queryFn: () => apiFetch<DashboardLayoutOut>(`/api/v1/dashboard-layouts/${page}`),
    enabled: Boolean(user),
    staleTime: Infinity, // user-private; refreshed explicitly on save/reset
  });
}

export function useSaveDashboardLayout(page: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (layout: GridLayouts) =>
      apiFetch<DashboardLayoutOut>(`/api/v1/dashboard-layouts/${page}`, {
        method: "PUT",
        body: JSON.stringify({ layout }),
      }),
    onSuccess: (data) => queryClient.setQueryData(["dashboard-layout", page], data),
  });
}

export function useResetDashboardLayout(page: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<DashboardLayoutOut>(`/api/v1/dashboard-layouts/${page}/reset`, {
        method: "POST",
      }),
    onSuccess: (data) => queryClient.setQueryData(["dashboard-layout", page], data),
  });
}

// ── Saved reports ─────────────────────────────────────────────────────────────
export interface SavedReportInput {
  name: string;
  description?: string | null;
  filters: Record<string, unknown>;
  columns: string[];
  group_by: string;
}

export function useSavedReports() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["saved-reports"],
    queryFn: () => apiFetch<SavedReport[]>("/api/v1/reports"),
    enabled: Boolean(user),
  });
}

export function useSharedReports() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["shared-reports"],
    queryFn: () => apiFetch<SavedReport[]>("/api/v1/reports/shared-with-me"),
    enabled: Boolean(user),
  });
}

export function usePendingShares(enabled: boolean) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["pending-shares"],
    queryFn: () => apiFetch<ShareOut[]>("/api/v1/reports/shares/pending"),
    enabled: Boolean(user) && enabled,
  });
}

export function useCreateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SavedReportInput) =>
      apiFetch<SavedReport>("/api/v1/reports", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-reports"] }),
  });
}

export function useDeleteReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/reports/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-reports"] }),
  });
}

export function useRunReport() {
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<ReportRunResult>(`/api/v1/reports/${id}/run`, { method: "POST" }),
  });
}

// ── Sharing lifecycle ─────────────────────────────────────────────────────────
export function useShareReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, sharedWith }: { reportId: string; sharedWith: string }) =>
      apiFetch<ShareOut>(`/api/v1/reports/${reportId}/share`, {
        method: "POST",
        body: JSON.stringify({ shared_with: sharedWith }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pending-shares"] }),
  });
}

export function useDecideShare(decision: "approve" | "reject") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (shareId: string) =>
      apiFetch<ShareOut>(`/api/v1/reports/shares/${shareId}/${decision}`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-shares"] });
      queryClient.invalidateQueries({ queryKey: ["shared-reports"] });
    },
  });
}

// ── Admin: users ──────────────────────────────────────────────────────────────
export interface ScopeInput {
  scope_type: string;
  scope_value: string | null;
}

export interface UserCreateInput {
  firebase_uid: string;
  email: string;
  display_name?: string | null;
  roles: string[];
  scopes: ScopeInput[];
}

export interface UserUpdateInput {
  display_name?: string | null;
  is_active?: boolean;
  roles?: string[];
  scopes?: ScopeInput[];
}

export function useAdminUsers() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<AdminUser[]>("/api/v1/admin/users"),
    enabled: Boolean(user),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreateInput) =>
      apiFetch<AdminUser>("/api/v1/admin/users", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UserUpdateInput }) =>
      apiFetch<AdminUser>(`/api/v1/admin/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

// ── Admin: roles ──────────────────────────────────────────────────────────────
export function useAdminRoles() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["admin-roles"],
    queryFn: () => apiFetch<RoleConfig[]>("/api/v1/admin/roles"),
    enabled: Boolean(user),
  });
}

export function useUpdateRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      metricGroups,
      capabilities,
    }: {
      id: number;
      metricGroups: string[];
      capabilities: string[];
    }) =>
      apiFetch<RoleConfig>(`/api/v1/admin/roles/${id}`, {
        method: "PUT",
        body: JSON.stringify({ metric_groups: metricGroups, capabilities }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-roles"] }),
  });
}

// ── Admin: revenue targets ──────────────────────────────────────────────────
export function useTargets(year: number) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["targets", year],
    queryFn: () => apiFetch<TargetsResponse>(`/api/v1/meta/targets?year=${year}`),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

export interface TargetInput {
  period_type: "year" | "month";
  period_year: number;
  period_month?: number | null;
  target_usd: number;
}

export function useSetTarget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TargetInput) =>
      apiFetch<RevenueTarget>("/api/v1/admin/targets", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["targets", variables.period_year] });
    },
  });
}

// ── Admin: audit + data health ──────────────────────────────────────────────
export interface AuditFilters {
  action?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export function useAudit(filters: AuditFilters) {
  const { user } = useAuth();
  const params = {
    action: filters.action,
    date_from: filters.date_from,
    date_to: filters.date_to,
    limit: filters.limit ?? 50,
    offset: filters.offset ?? 0,
  };
  return useQuery({
    queryKey: ["audit", params],
    queryFn: () => apiFetch<AuditPage>(`/api/v1/admin/audit${buildQuery(params)}`),
    enabled: Boolean(user),
  });
}

export function useAuditActions() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["audit-actions"],
    queryFn: () => apiFetch<string[]>("/api/v1/admin/audit/actions"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

export function useDataHealth() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["data-health"],
    queryFn: () => apiFetch<DataHealth>("/api/v1/admin/data-health"),
    enabled: Boolean(user),
    staleTime: 60 * 1000,
  });
}

// ── Admin: System tab (connection health, settings, sync) ───────────────────
export interface ConnectionStatus {
  name: string;
  status: "up" | "down" | "not_configured";
  latency_ms: number | null;
  detail: string | null;
}
export interface SystemHealth {
  postgres: ConnectionStatus;
  redis: ConnectionStatus;
  bigquery: ConnectionStatus;
}
export interface AppSetting {
  key: string;
  type: string;
  value: number | boolean | string;
  default: number | boolean | string;
  label: string;
  description: string;
  group: string;
  minimum: number | null;
  maximum: number | null;
  updated_at: string | null;
}
export interface SyncTriggerResult {
  triggered: boolean;
  configured: boolean;
  message: string;
}
export interface ClientSettings {
  data_freshness_threshold_hours: number;
  show_demo_widgets: boolean;
}

export function useSystemHealth() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["system-health"],
    queryFn: () => apiFetch<SystemHealth>("/api/v1/admin/system/health"),
    enabled: Boolean(user),
    refetchInterval: 30 * 1000, // live-ish status
  });
}

export function useAppSettings() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["app-settings"],
    queryFn: () => apiFetch<AppSetting[]>("/api/v1/admin/settings"),
    enabled: Boolean(user),
  });
}

export function useUpdateSetting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: number | boolean | string }) =>
      apiFetch<AppSetting>(`/api/v1/admin/settings/${encodeURIComponent(key)}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
      queryClient.invalidateQueries({ queryKey: ["client-settings"] });
      queryClient.invalidateQueries({ queryKey: ["data-health"] });
    },
  });
}

export function useRunSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<SyncTriggerResult>("/api/v1/admin/system/sync", { method: "POST" }),
    onSuccess: () => {
      // A completed run (local path) updates history/status; refresh both surfaces.
      queryClient.invalidateQueries({ queryKey: ["integration-status"] });
      queryClient.invalidateQueries({ queryKey: ["data-health"] });
      queryClient.invalidateQueries({ queryKey: ["system-health"] });
    },
  });
}

/** Operational settings any authenticated user may read (e.g. demo-widget toggle). */
export function useClientSettings() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["client-settings"],
    queryFn: () => apiFetch<ClientSettings>("/api/v1/meta/settings"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

// ── Admin: Integration tab (BigQuery → Postgres) ────────────────────────────
export interface IntegrationStatus {
  bigquery: ConnectionStatus;
  postgres: ConnectionStatus;
  redis: ConnectionStatus;
  last_sync: SyncRunOut | null;
  recent_syncs: SyncRunOut[];
}
export interface BigQueryTestResult {
  ok: boolean;
  message: string;
}

export function useIntegrationStatus() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["integration-status"],
    queryFn: () => apiFetch<IntegrationStatus>("/api/v1/admin/integration/status"),
    enabled: Boolean(user),
    refetchInterval: 30 * 1000, // live-ish status
  });
}

export function useTestBigQuery() {
  return useMutation({
    mutationFn: () =>
      apiFetch<BigQueryTestResult>("/api/v1/admin/integration/test-bigquery", {
        method: "POST",
      }),
  });
}

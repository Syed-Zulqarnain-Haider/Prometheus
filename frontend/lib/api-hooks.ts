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

export interface FilterOptions {
  platforms: string[];
  consoles: string[];
  pod_owners: string[];
  publishers: string[];
  developers: string[];
  google_play_accounts: string[];
  apple_accounts: string[];
  packages: string[];
  bundles: string[];
  hous: string[];
  apps: { value: string; label: string | null }[];
}

/** Resolve real iOS store icons for the given apple_ids (cached server-side). Returns a
 *  { "<apple_id>": url } map; ids without an icon are simply absent. */
export function useAppIcons(appleIds: (number | null | undefined)[]) {
  const { user } = useAuth();
  const ids = Array.from(new Set(appleIds.filter((x): x is number => Boolean(x)))).sort(
    (a, b) => a - b,
  );
  return useQuery({
    queryKey: ["app-icons", ids],
    queryFn: () =>
      apiFetch<Record<string, string>>(
        `/api/v1/apps/icons${buildQuery({ ids: ids.map(String) })}`,
      ),
    enabled: Boolean(user) && ids.length > 0,
    staleTime: 60 * 60 * 1000,
  });
}

/** Cascading filter-bar options — refetches whenever any filter changes, so each dropdown
 *  reflects the others (e.g. platform=ios narrows the HOU list). */
export function useFilterOptions(filters: Filters) {
  const { user } = useAuth();
  const params = filtersToApiQuery(filters);
  return useQuery({
    queryKey: ["filter-options", params],
    queryFn: () => apiFetch<FilterOptions>(`/api/v1/meta/filter-options${buildQuery(params)}`),
    enabled: Boolean(user),
    staleTime: 60 * 1000,
    placeholderData: (prev) => prev, // keep old options visible while the new set loads
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

/** A shared-report recipient requests edit access (routes to owner + admins). */
export function useRequestReportEdit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reportId: string) =>
      apiFetch<ShareOut>(`/api/v1/reports/${reportId}/request-edit`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["shared-reports"] }),
  });
}

/** Owner/admin grants or revokes a recipient's edit request. */
export function useDecideReportEdit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ shareId, grant }: { shareId: string; grant: boolean }) =>
      apiFetch<ShareOut>(`/api/v1/reports/shares/${shareId}/edit-decision`, {
        method: "POST",
        body: JSON.stringify({ grant }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-shares"] });
      queryClient.invalidateQueries({ queryKey: ["shared-reports"] });
    },
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
  access_expires_at?: string | null;
  access_duration_days?: number;
}

export interface UserUpdateInput {
  display_name?: string | null;
  is_active?: boolean;
  roles?: string[];
  scopes?: ScopeInput[];
  access_expires_at?: string | null;
  access_duration_days?: number;
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

export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/v1/admin/users/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

// ── Access requests (Google sign-in → admin approves/rejects) ──────────────────
export interface AccessRequest {
  id: string;
  firebase_uid: string;
  email: string;
  display_name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ApproveAccessInput {
  roles: string[];
  scopes: ScopeInput[];
  access_duration_days?: number;
  access_expires_at?: string | null;
}

/** Lodge a pending access request (authenticated-but-unprovisioned caller). */
export function useRequestAccess() {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ status: string }>("/api/v1/auth/access-request", { method: "POST" }),
  });
}

export function useAccessRequests() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["access-requests"],
    queryFn: () => apiFetch<AccessRequest[]>("/api/v1/admin/access-requests"),
    enabled: Boolean(user),
  });
}

export function useApproveAccessRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ApproveAccessInput }) =>
      apiFetch<AdminUser>(`/api/v1/admin/access-requests/${id}/approve`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["access-requests"] });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });
}

export function useRejectAccessRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<AccessRequest>(`/api/v1/admin/access-requests/${id}/reject`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["access-requests"] }),
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
export interface AlertFinding {
  key: string;
  severity: string;
  title: string;
  body: string;
}
export interface AlertsEvaluateResult {
  count: number;
  fired: AlertFinding[];
}

/** Run the anomaly-alert checks now (admin). Returns what fired; refreshes notifications. */
export function useEvaluateAlerts() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<AlertsEvaluateResult>("/api/v1/admin/alerts/evaluate", { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export interface DigestResult {
  sent: boolean;
  preview: string | null;
}

/** Build + send the daily digest now (admin). Returns a preview of what was sent. */
export function useSendDigest() {
  return useMutation({
    mutationFn: () => apiFetch<DigestResult>("/api/v1/admin/digest/send", { method: "POST" }),
  });
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

export interface RunSyncOpts {
  mode?: "incremental" | "full" | "range";
  start?: string; // YYYY-MM-DD (range mode)
  end?: string; // YYYY-MM-DD (range mode)
}

export function useRunSync() {
  const queryClient = useQueryClient();
  return useMutation({
    // incremental (default) = rolling-window overwrite; full = backfill all history;
    // range = overwrite an explicit start..end window.
    mutationFn: (opts?: RunSyncOpts) => {
      const params = new URLSearchParams({ mode: opts?.mode ?? "incremental" });
      if (opts?.start) params.set("start", opts.start);
      if (opts?.end) params.set("end", opts.end);
      return apiFetch<SyncTriggerResult>(`/api/v1/admin/system/sync?${params.toString()}`, {
        method: "POST",
      });
    },
    onSuccess: () => {
      // A completed run (local path) updates history/status; refresh both surfaces.
      queryClient.invalidateQueries({ queryKey: ["integration-status"] });
      queryClient.invalidateQueries({ queryKey: ["data-health"] });
      queryClient.invalidateQueries({ queryKey: ["system-health"] });
    },
  });
}

// ── Ask-your-data assistant (chatbot) ───────────────────────────────────────
export interface ChatProvider {
  id: string;
  label: string;
}

export interface ChatStatus {
  available: boolean;
  configured: boolean;
  enabled: boolean;
  providers: ChatProvider[];
  reason: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  answer: string;
  tool_calls: number;
  provider: string;
}

/** Whether the assistant is usable for this user (admin-enabled AND a provider configured),
 * plus the list of LLM providers they can pick from. */
export function useChatStatus() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["chat-status"],
    queryFn: () => apiFetch<ChatStatus>("/api/v1/chat/status"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

/** Send the running transcript on the chosen provider; the last message must be the user's
 * question. Answers are always scoped to the caller's own access, whichever provider. */
export function useSendChat() {
  return useMutation({
    mutationFn: ({ messages, provider }: { messages: ChatMessage[]; provider?: string }) =>
      apiFetch<ChatResponse>("/api/v1/chat", {
        method: "POST",
        body: JSON.stringify({ messages, provider }),
      }),
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

export interface SchemaColumnDiff {
  column: string;
  expected: string;
  actual: string;
}
export interface BigQueryColumn {
  column: string;
  data_type: string;
}
export interface SchemaDiff {
  configured: boolean;
  in_sync: boolean;
  message: string | null;
  missing_in_view: string[];
  optional_absent: string[];
  type_mismatches: SchemaColumnDiff[];
  unregistered_in_view: BigQueryColumn[];
}
export interface ClearDataResult {
  cleared: boolean;
  rows_deleted: Record<string, number>;
  total: number;
}

export interface SchemaSyncColumn {
  name: string;
  type: string;
  reason: string | null;
}
export interface SchemaSyncResult {
  configured: boolean;
  ok: boolean;
  message: string | null;
  added: SchemaSyncColumn[];
  reactivated: string[];
  deactivated: string[];
  healed_static: string[];
  missing_in_bigquery: string[];
  unsupported_types: SchemaSyncColumn[];
}

/** Read-only, on-demand schema diff (BigQuery view vs the metric registry). */
export function useSchemaDiff() {
  return useMutation({
    mutationFn: () => apiFetch<SchemaDiff>("/api/v1/admin/integration/schema-diff"),
  });
}

/** Match Database & BigQuery Schema for the metrics fact table (admin-only, additive). */
export function useSchemaSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<SchemaSyncResult>("/api/v1/admin/integration/schema-sync", { method: "POST" }),
    // New/updated columns can change what dashboards can request — refresh everything.
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

/** DESTRUCTIVE: wipe analytics/fact data. Requires the exact confirmation phrase. */
export function useClearData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (confirmation: string) =>
      apiFetch<ClearDataResult>("/api/v1/admin/integration/clear-data", {
        method: "POST",
        body: JSON.stringify({ confirmation }),
      }),
    // Clearing ALL fact data invalidates every dashboard/aggregate query, not just the
    // integration views — invalidate the whole cache so nothing keeps showing pre-clear data.
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

// ── App Master (admin-only: view + edit the BigQuery app_master_v2 table) ───────
export interface AppMasterColumnMeta {
  name: string;
  type: "text" | "bigint" | "boolean" | "double" | "timestamptz";
  editable: boolean;
}

export interface AppMasterListResponse {
  rows: Record<string, unknown>[];
  total: number;
  columns: AppMasterColumnMeta[];
  column_order: string[];
  primary_key: string;
}

export interface AppMasterFilters {
  search: string;
  platform: string; // "" = all
  hou: string; // "" = all
  publisher: string; // "" = all
  pod: string; // raw input; sent as int when numeric
  needsReview: "" | "true" | "false";
  package: string;
  appId: string;
}

export function useAppMaster(filters: AppMasterFilters, limit: number, offset: number) {
  const { user } = useAuth();
  const params: Record<string, string | number | boolean> = { limit, offset };
  if (filters.search.trim()) params.search = filters.search.trim();
  if (filters.platform) params.platform = filters.platform;
  if (filters.hou) params.hou = filters.hou;
  if (filters.publisher) params.publisher = filters.publisher;
  if (filters.pod.trim() && Number.isInteger(Number(filters.pod))) params.pod = Number(filters.pod);
  if (filters.needsReview) params.needs_review = filters.needsReview;
  if (filters.package.trim()) params.package = filters.package.trim();
  if (filters.appId.trim()) params.app_id = filters.appId.trim();
  return useQuery({
    queryKey: ["app-master", params],
    queryFn: () => apiFetch<AppMasterListResponse>(`/api/v1/app-master${buildQuery(params)}`),
    enabled: Boolean(user),
  });
}

export interface AppMasterFilterValues {
  platforms: string[];
  hou: string[];
  publishers: string[];
  pods: number[];
}

/** Distinct values for the App Master filter dropdowns. */
export function useAppMasterFilterValues() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["app-master-filter-values"],
    queryFn: () => apiFetch<AppMasterFilterValues>("/api/v1/app-master/filter-values"),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });
}

/** Set the GLOBAL column order (admin) — applies to every user's grid. */
export function useSetAppMasterColumnOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (order: string[]) =>
      apiFetch<string[]>("/api/v1/app-master/column-order", {
        method: "PUT",
        body: JSON.stringify({ order }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["app-master"] }),
  });
}

/** Undo the most recent edit on a row (restores prior values in BigQuery + Postgres). */
export function useUndoAppMaster() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (key: string) =>
      apiFetch<Record<string, unknown>>(`/api/v1/app-master/${encodeURIComponent(key)}/undo`, {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["app-master"] }),
  });
}

/** Edit one row's editable columns (writes to BigQuery first, then the serving copy). */
export function useUpdateAppMaster() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, body }: { key: string; body: Record<string, unknown> }) =>
      apiFetch<Record<string, unknown>>(`/api/v1/app-master/${encodeURIComponent(key)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["app-master"] }),
  });
}

/** Re-pull the whole table from BigQuery into the Postgres serving copy. */
export function useRefreshAppMaster() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ synced: number; skipped: number }>("/api/v1/app-master/refresh", {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["app-master"] }),
  });
}

/** On-demand check that the configured BigQuery table's columns match the registry. */
export function useAppMasterSchemaDiff() {
  return useMutation({
    mutationFn: () => apiFetch<SchemaDiff>("/api/v1/app-master/schema-diff"),
  });
}

/** Match Database & BigQuery Schema for App Master (admin-only, additive, non-destructive). */
export function useAppMasterSchemaSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<SchemaSyncResult>("/api/v1/app-master/schema-sync", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["app-master"] }),
  });
}

// ── Notifications (RBAC-scoped) + real-time polling ──────────────────────────────
export interface NotificationItem {
  id: number;
  created_at: string;
  type: string;
  title: string;
  body: string | null;
  severity: "info" | "warning" | "critical";
  link: string | null;
  resource: string | null;
  read: boolean;
}

export interface NotificationList {
  items: NotificationItem[];
  unread: number;
}

/** Near-real-time: polls every 15s AND refetches the moment the tab regains focus, so
 *  notifications (and cross-user changes) surface without a manual refresh. */
export function useNotifications() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiFetch<NotificationList>("/api/v1/notifications"),
    enabled: Boolean(user),
    refetchInterval: 15000,
    refetchOnWindowFocus: true,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/api/v1/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>("/api/v1/notifications/read-all", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

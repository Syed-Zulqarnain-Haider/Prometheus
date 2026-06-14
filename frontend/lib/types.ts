/** Shared API types mirroring the backend responses. */

export type Platform = "ios" | "android";

/** The backend error envelope: {"error": {"code", "message"}}. */
export interface ApiErrorBody {
  error: { code: string; message: string };
}

export interface AppListItem {
  canonical_key: string;
  app_name: string | null;
  publisher: string | null;
  pod: string | null;
  pod_owner: string | null;
  hou: string | null;
  is_mapped: boolean | null;
}

export interface AppsResponse {
  apps: AppListItem[];
}

export interface AppDetail {
  canonical_key: string;
  app_name: string | null;
  publisher: string | null;
  pod: string | null;
  pod_owner: string | null;
  hou: string | null;
  app_category: string | null;
  ownership_type: string | null;
  is_mapped: boolean | null;
  apple_id: number | null;
  android_package: string | null;
  ios_bundle_id: string | null;
}

export interface Freshness {
  bq_built_at: string | null;
  last_status: string | null;
  last_run_finished_at: string | null;
  rows_loaded: number | null;
}

export type Bucket = "day" | "week" | "month";
export type MetricValue = number | string | null;

export interface SummaryResponse {
  current: Record<string, number | null>;
  previous: Record<string, number | null> | null;
}

export interface TimeseriesResponse {
  bucket: Bucket;
  metrics: string[];
  series: Record<string, MetricValue>[];
}

export interface BreakdownResponse {
  group_by: string;
  rows: Record<string, MetricValue>[];
}

export interface TableResponse {
  rows: Record<string, MetricValue>[];
  next_cursor: string | null;
}

/** /auth/me payload (roles, metric groups, capabilities, scopes). */
export interface UserContext {
  user_id: string;
  email: string;
  display_name: string | null;
  roles: string[];
  metric_groups: string[];
  capabilities: string[];
  scopes: { scope_type: string; scope_value: string | null }[];
}

/** /auth/directory entry — a share-recipient candidate. */
export interface DirectoryEntry {
  user_id: string;
  email: string;
  display_name: string | null;
}

export type ReportGroupBy = "app" | "pod" | "publisher" | "platform" | "hou" | "date";
export type ExportFormat = "csv" | "xlsx" | "gsheet";
export type ShareStatus = "pending" | "approved" | "rejected" | "revoked";

export interface SavedView {
  id: string;
  name: string;
  page: string;
  filters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SavedReport {
  id: string;
  name: string;
  description: string | null;
  filters: Record<string, unknown>;
  columns: string[];
  group_by: string;
  sort: Record<string, unknown> | null;
  owner_id: string;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReportRunResult {
  group_by: string;
  columns: string[];
  rows: Record<string, MetricValue>[];
}

export interface ShareOut {
  id: string;
  report_id: string;
  report_name: string | null;
  shared_by: string;
  shared_with: string;
  status: ShareStatus;
  created_at: string;
}

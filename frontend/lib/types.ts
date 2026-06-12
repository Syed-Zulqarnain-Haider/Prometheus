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

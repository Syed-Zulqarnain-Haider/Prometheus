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

export interface Freshness {
  bq_built_at: string | null;
  last_status: string | null;
  last_run_finished_at: string | null;
  rows_loaded: number | null;
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

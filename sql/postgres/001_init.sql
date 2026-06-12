-- ============================================================================
-- 001_init.sql — Foundation schema (everything except the generated fact table,
-- which is 002_fact_table.sql, emitted from metric_registry.py).
-- Target: PostgreSQL 15+ (Cloud SQL), private IP, SSL required.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ── App dimension (latest mapping per app, refreshed by sync) ───────────────
CREATE TABLE dim_app (
  canonical_key   TEXT PRIMARY KEY,
  app_name        TEXT,
  apple_id        BIGINT,
  android_package TEXT,
  ios_bundle_id   TEXT,
  publisher       TEXT,
  pod             TEXT,
  pod_owner       TEXT,
  hou             TEXT,
  app_category    TEXT,
  ownership_type  TEXT,
  is_mapped       BOOLEAN,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Identity & RBAC ─────────────────────────────────────────────────────────
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  firebase_uid  TEXT UNIQUE NOT NULL,
  email         TEXT UNIQUE NOT NULL,
  display_name  TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    UUID REFERENCES users(id)
);

CREATE TABLE roles (
  id   SMALLSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE user_roles (
  user_id UUID     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id SMALLINT NOT NULL REFERENCES roles(id),
  PRIMARY KEY (user_id, role_id)
);

-- Metric-group permissions per role — DATA, admin-editable, no deploys
CREATE TABLE role_metric_permissions (
  role_id      SMALLINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  metric_group TEXT NOT NULL CHECK (metric_group IN
    ('store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability')),
  PRIMARY KEY (role_id, metric_group)
);

-- Capability flags per role (export / share_report / admin_panel) — admin-editable
CREATE TABLE role_capabilities (
  role_id    SMALLINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  capability TEXT NOT NULL CHECK (capability IN ('export','share_report','admin_panel')),
  PRIMARY KEY (role_id, capability)
);

-- Row-level scopes. Effective access = UNION of a user's rows.
-- "Restrict marketing to one app tomorrow" = data edit here, zero code changes.
CREATE TABLE user_scopes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  scope_type  TEXT NOT NULL CHECK (scope_type IN ('all','hou','pod','publisher','app')),
  scope_value TEXT,
  granted_by  UUID REFERENCES users(id),
  granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT scope_value_required
    CHECK ( (scope_type = 'all' AND scope_value IS NULL)
         OR (scope_type <> 'all' AND scope_value IS NOT NULL) ),
  UNIQUE (user_id, scope_type, scope_value)
);
CREATE INDEX idx_scopes_user ON user_scopes (user_id);

-- ── Saved views / reports / admin-approval sharing ──────────────────────────
CREATE TABLE saved_views (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  page       TEXT NOT NULL,
  filters    JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_views_user ON saved_views (user_id);

CREATE TABLE saved_reports (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  description TEXT,
  filters     JSONB NOT NULL,
  columns     JSONB NOT NULL,  -- re-validated against the CALLER's permitted groups on read & write
  group_by    TEXT  NOT NULL CHECK (group_by IN ('app','pod','publisher','platform','hou','date')),
  sort        JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reports_user ON saved_reports (user_id);

CREATE TABLE report_shares (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id   UUID NOT NULL REFERENCES saved_reports(id) ON DELETE CASCADE,
  shared_by   UUID NOT NULL REFERENCES users(id),
  shared_with UUID NOT NULL REFERENCES users(id),
  status      TEXT NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','approved','rejected','revoked')),
  approved_by UUID REFERENCES users(id),
  approved_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (report_id, shared_with)
);
CREATE INDEX idx_shares_pending ON report_shares (status) WHERE status = 'pending';

-- ── Audit log (append-only; API role gets INSERT+SELECT only) ───────────────
CREATE TABLE audit_log (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    UUID REFERENCES users(id),
  action     TEXT NOT NULL,
  resource   TEXT,
  detail     JSONB,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_user_time   ON audit_log (user_id, created_at DESC);
CREATE INDEX idx_audit_action_time ON audit_log (action,  created_at DESC);

-- ── Sync state ───────────────────────────────────────────────────────────────
CREATE TABLE sync_runs (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ,
  status        TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','success','schema_mismatch','failed')),
  rows_loaded   BIGINT,
  rows_previous BIGINT,
  bq_built_at   TIMESTAMPTZ,
  error_detail  TEXT
);

-- ── Seed: roles, permissions (marketing INCLUDES iap per owner decision) ────
INSERT INTO roles (name) VALUES
  ('admin'), ('executive'), ('pod_owner'), ('marketing'), ('finance'), ('viewer');

INSERT INTO role_metric_permissions (role_id, metric_group)
SELECT r.id, g.g
FROM roles r
JOIN LATERAL (
  SELECT unnest(CASE r.name
    WHEN 'admin'     THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']
    WHEN 'executive' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']
    WHEN 'pod_owner' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']
    WHEN 'marketing' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','profitability']
    WHEN 'finance'   THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','profitability']
    WHEN 'viewer'    THEN ARRAY['store_installs']
  END) AS g
) g ON true;

INSERT INTO role_capabilities (role_id, capability)
SELECT r.id, c.c
FROM roles r
JOIN LATERAL (
  SELECT unnest(CASE r.name
    WHEN 'admin'     THEN ARRAY['export','share_report','admin_panel']
    WHEN 'executive' THEN ARRAY['export','share_report']
    WHEN 'pod_owner' THEN ARRAY['export','share_report']
    WHEN 'marketing' THEN ARRAY['export','share_report']
    WHEN 'finance'   THEN ARRAY['export','share_report']
    ELSE ARRAY[]::text[]
  END) AS c
) c ON true;

-- ── Least-privilege DB roles ─────────────────────────────────────────────────
-- Run as the Cloud SQL superuser. Passwords come from Secret Manager at deploy.
-- api_service: serves the dashboard. NO UPDATE/DELETE on audit_log → tamper-evident.
-- sync_service: owns fact loading. Cannot touch users/RBAC tables.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_service') THEN
    CREATE ROLE api_service LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sync_service') THEN
    CREATE ROLE sync_service LOGIN;
  END IF;
END $$;

GRANT SELECT ON dim_app TO api_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, user_roles, user_scopes,
  role_metric_permissions, role_capabilities,
  saved_views, saved_reports, report_shares TO api_service;
GRANT SELECT ON roles, sync_runs TO api_service;
GRANT SELECT, INSERT ON audit_log TO api_service;          -- append-only
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO api_service;

GRANT SELECT, INSERT, UPDATE ON sync_runs TO sync_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON dim_app TO sync_service;
GRANT CREATE ON SCHEMA public TO sync_service;             -- staging create/swap
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO sync_service;
-- (fact table SELECT for api_service is granted in 002 after the table exists,
--  and re-granted by the sync job after every swap.)

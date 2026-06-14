# CLAUDE.md — Prometheus Performance Dashboard

This file is the permanent project memory. Read it fully before any task.
Decisions here are FINAL unless the owner explicitly changes them in the session.

## What we are building
An enterprise analytics dashboard (replacing a Looker Studio dashboard) for mobile-app
performance data. ~50 internal users at launch. Data source: BigQuery. Serving: PostgreSQL.

## Architecture (LOCKED — do not propose alternatives)
- **Frontend**: Next.js 14+ App Router, TypeScript strict, Tailwind + shadcn/ui,
  Apache ECharts (`echarts-for-react`, tree-shaken imports), TanStack Table + Virtual + Query.
  Deployed on Vercel.
- **Backend**: FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.0 + Alembic, on Cloud Run.
- **Serving DB**: PostgreSQL on **Neon** (serverless, pooled connection string). Users/API
  never query BigQuery. SECURITY TRADE-OFF (accepted): Neon is reached over the public
  internet via TLS with strong, Secret-Manager-held credentials — NOT a private IP as a
  Cloud SQL deployment would allow. This is a deliberate cost/ops choice for ~50 users;
  mitigations are TLS-required connections, least-privilege DB roles, and rotated secrets.
  Migrating back to Cloud SQL (private IP) later remains possible — the app code is
  connection-string agnostic, so only env/secrets and networking change.
- **Cache**: Redis as a lightweight container running alongside the API (not Memorystore),
  key prefix `agg:*`, busted by the daily sync.
- **Auth**: Firebase Auth. JWT verified server-side (firebase-admin) on EVERY route.
- **Data flow**: BigQuery view `terafort.api.daily_performance_v1` → daily sync job
  (Cloud Run Job, ~06:00 UTC) → `fact_daily_performance` in Postgres via staged load +
  atomic swap. On any sync failure: keep serving yesterday's data, alert, record in `sync_runs`.

## The contract rules (NEVER violate)
1. The app reads ONLY the BigQuery view `daily_performance_v1`, never the underlying table
   `terafort.Final_Staging_tables.unified_daily_performance`.
2. `backend/app/core/metric_registry.py` is the SINGLE SOURCE OF TRUTH for all 78 fact
   columns and their metric groups. Pydantic models, RBAC column filters, sync validation,
   and DDL are GENERATED from it. To add a column: add a registry entry + Alembic migration.
   Never hand-write column lists anywhere else.
3. Ad revenue = AdMob + AppLovin only. Mintegral publisher is EXCLUDED by design
   (double-counts inside AdMob mediation). Never "fix" this.
4. `total_revenue_usd = total_iap_net_usd + total_ad_revenue_usd`. Derived metrics
   (roas, ad_roas, profit_usd, cpi*, *_ecpm, *_ctr, organic_install_share) are computed
   in the BigQuery view, NOT in Python/TS.

## RBAC (server-side ONLY; frontend hiding is cosmetic)
- Roles: admin, executive, pod_owner, marketing, finance, viewer.
- Row scope: `user_scopes(scope_type ∈ all|hou|pod|publisher|app, scope_value)` —
  effective access = UNION of rows. WHERE clauses are injected from the token's resolved
  scopes. Client filter params may only NARROW, never widen.
- Metric scope: `role_metric_permissions` (groups: store_installs, ua_spend, ad_revenue,
  iap_revenue, attribution, profitability). Forbidden columns are never serialized —
  per-role Pydantic models generated from the metric registry.
- Capabilities: `role_capabilities` (export, share_report, admin_panel).
- Marketing INCLUDES iap_revenue (owner decision). Viewer = store_installs only, no export.
- Report sharing: non-admin share → `report_shares.status='pending'` → any admin approves.
  Admin shares are auto-approved. Recipients ALWAYS view through their OWN scopes/permissions
  — access is never transferable via sharing.
- Out-of-scope resources return 404 (indistinguishable from nonexistent), not 403.

## Security rules (NEVER violate)
- No secrets in code, .env files in git, or logs. GCP Secret Manager only. `.env.example` only.
- SQLAlchemy parameterized queries exclusively. NEVER build SQL with f-strings/concat
  from user input. (The sync job's f-string DDL is allowed: identifiers come from the
  registry, never from users.)
- audit_log is append-only: write via INSERT only; the api_service DB role has no
  UPDATE/DELETE on it. Log: login, view_page, api_query, export, report/share lifecycle,
  all admin actions — with ip, user_agent, and filter detail JSONB.
- Exports re-run server-side through the caller's RBAC and are always audit-logged.
  Formats: CSV, XLSX (openpyxl), Google Sheets (Sheets API via user OAuth). NO PDF in v1.
- Rate limiting: per-user sliding window in Redis (300/min general, 10/min export) + edge.
- Error responses: `{"error": {"code": "...", "message": "..."}}` — never stack traces or SQL.
- CORS: exact frontend origin only (env-configured; .vercel.app during dev).

## Explicit v1 exclusions (do NOT build, even if it seems helpful)
- NO Adjust/attribution dashboard features (data syncs to Postgres; columns may appear
  as optional Apps Explorer columns ONLY).
- NO uninstall_rate metric (raw gp_uninstalls column is shown; the rate is excluded by owner).
- NO PDF export. NO partner API (designed-in for later; tables/keys exist on paper only).
- NO localStorage for app state in artifacts/components where SSR runs.

## Data quirks to handle in UI
- Apple data lags ~2-3 days; current-day rows are often Adjust-only or zero-filled.
  Always show the "data as of" banner from `sync_runs.bq_built_at` / `/meta/freshness`.
  Never present source-lag zeros as real zeros where avoidable.
- `is_mapped = false` apps exist; Data Health page lists them.
- `platform ∈ {ios, android}`; iOS keys on `apple_id`, Android on `android_package`,
  `canonical_key` links both. `app_key` (generated column) = COALESCE of the three.

## Repository layout
```
backend/app/{main.py, core/, models/, schemas/, api/v1/, services/, sync/}
backend/{alembic/, tests/}
frontend/{app/, components/{charts,tables,filters,layout}/, lib/, tests/}
.github/workflows/{ci.yml, deploy-backend.yml, deploy-frontend.yml}
docs/  (the technical spec + this file's source decisions)
```
Step 1 (DONE, in repo): sql/bigquery/daily_performance_v1.sql, sql/postgres/001+002,
sync/metric_registry.py, sync/sync_job.py, Dockerfile. Reuse — do not rewrite.

## Build order (work ONLY on the current step unless told otherwise)
1. ✅ Data foundation: BQ view, Postgres DDL, sync job
2. Auth + RBAC core: Firebase verify, UserContext dependency, scope resolver,
   per-role response-model generation from the registry, audit middleware
3. Metrics API: /metrics/summary, /timeseries, /breakdown, /table, /apps, /apps/{key},
   query-builder service (scope→WHERE injection), Redis caching, /meta/freshness
4. Frontend shell: auth flow, layout, global URL-synced filter bar, ECharts theme
5. Executive Overview page (first visible win), then Revenue, UA, Store, Apps Explorer,
   App Detail
6. Saved views + report builder + admin-approval sharing + exports
7. Admin panel + audit viewer + Data Health page
8. CI/CD hardening, rate limiting, Cloud Armor config, deploy docs

## Engineering conventions
- Python: ruff + mypy --strict pass required. Pytest for every service & route;
  RBAC matrix tests (every role × representative endpoints) are mandatory in step 2-3.
- TypeScript: strict mode, eslint clean. No `any`. Components small and typed.
- Conventional commits. Small PR-sized changes per task. Never commit generated
  __pycache__/node_modules/.env.
- Tests must pass locally before claiming a step done. If something can't be tested
  locally (needs GCP), say so explicitly — never claim untested things work.
- When uncertain about a requirement, ASK the owner; do not invent features.

## Merge & branching policy (standing — applies to every step, no need to ask)
- Before starting each new step, RESET the working branch to the latest `origin/main`
  (`git fetch origin main && git reset --hard origin/main`, then force-push). This
  prevents the squash-merge divergence conflicts seen in step 2.2.
- After completing a step: if `ruff`, `mypy --strict`, and ALL tests pass, open a PR
  and squash-merge it to `main` automatically — no need to ask. If ANY check fails,
  do NOT merge: leave the work on the branch and report the failure to the owner.
- Never merge with failing or skipped checks. State explicitly anything that could not
  be verified locally (e.g. needs GCP/Firebase).


## Owner preferences
- Address the owner as "Yes Boss" / "Mohtaram" at the start of responses.
- Be direct about problems and trade-offs. Never hallucinate APIs, versions, or claims.
- Production-grade quality bar: input validation everywhere, no silent failures,
  visible degradation, everything audit-trailed.

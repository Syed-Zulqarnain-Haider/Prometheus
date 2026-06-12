# CLAUDE CODE PLAYBOOK — exact prompts to run, in order

How to use this file, Boss:
1. Create the git repo, put `CLAUDE.md` at the ROOT, and copy the Step-1 package
   (sql/ and sync/ folders) into it. Commit.
2. Open Claude Code in the repo folder. It auto-reads CLAUDE.md every session.
3. Paste ONE prompt below per task. Review the diff, run the tests it tells you,
   commit, move to the next. Small tasks = better results + fewer tokens.
4. If Claude Code proposes changing a LOCKED decision, say:
   "Check CLAUDE.md — that decision is locked." It will course-correct.

Token-saving habits that actually work:
- One step per session; start fresh sessions per step (use /clear) so old context
  doesn't bloat every request.
- Never paste the spec into chat — it's already in CLAUDE.md / docs/. Just reference it.
- Ask for "plan first, then implement after I approve" on big tasks — cheaper than redoing.
- Keep tests green; failing-test loops burn the most tokens.

──────────────────────────────────────────────────────────────────────────────
STEP 2 — AUTH + RBAC CORE
──────────────────────────────────────────────────────────────────────────────

PROMPT 2.1 (scaffold):
"Read CLAUDE.md. Scaffold the FastAPI backend per the repository layout: main.py with
CORS from env, error-envelope exception handlers, /health route; core/config.py
(pydantic-settings, all secrets from env); SQLAlchemy 2.0 models for every table in
sql/postgres/001_init.sql (do not redesign them — mirror the DDL exactly); Alembic
initialized with an autogenerate baseline that matches the existing DDL; docker-compose.yml
for local Postgres+Redis; pytest + ruff + mypy configured. Plan first, wait for my approval."

PROMPT 2.2 (auth):
"Implement Firebase auth: verify Bearer JWT with firebase-admin in a dependency;
load user by firebase_uid; reject inactive users; POST /api/v1/auth/session (upserts
last-login audit entry) and GET /api/v1/auth/me returning roles, metric groups,
capabilities, scopes. Cache the resolved UserContext in Redis 5-min TTL. Unit tests
with a mocked token verifier — including: inactive user rejected, unknown uid rejected,
malformed token rejected."

PROMPT 2.3 (RBAC engine):
"Implement the RBAC core per CLAUDE.md: (a) scope resolver — user_scopes rows →
SQLAlchemy filter over fact_daily_performance ('all' short-circuits; else OR of
hou/pod/publisher conditions plus canonical_key IN for app scopes); (b) per-role
response-model generator that builds Pydantic models from metric_registry groups;
(c) capability dependency (require_capability('export') etc.). Write the RBAC matrix
test: for each role, assert exactly which metric groups serialize and that scope
filters compile to the expected SQL. This test suite is the wall — be exhaustive."

PROMPT 2.4 (audit):
"Implement the audit service: async write to audit_log (INSERT only) with action,
resource, detail JSONB, ip, user_agent; FastAPI middleware logging api_query for data
routes; explicit helpers for login/export/admin actions. Tests assert rows are written
and that the service never raises into the request path (log-and-continue on failure)."

──────────────────────────────────────────────────────────────────────────────
STEP 3 — METRICS API
──────────────────────────────────────────────────────────────────────────────

PROMPT 3.1:
"Implement services/query_builder.py: given UserContext + validated filter params
(date_from/date_to, compare, platform, pods[], publishers[], apps[]) produce SELECTs
over fact_daily_performance with the scope filter ALWAYS applied first; client filters
can only narrow. Aggregations: summary (totals + previous-period via date-shifted
window), timeseries (day|week|month buckets, chosen metrics), breakdown (group_by
app|pod|publisher|platform|hou with drill params), table (keyset pagination, sort
whitelist from the registry). Parameterized only. Tests with seeded fixture data
covering scope narrowing and period comparison math."

PROMPT 3.2:
"Wire routes /api/v1/metrics/{summary,timeseries,breakdown,table}, /api/v1/apps,
/api/v1/apps/{canonical_key} (404 when out of scope), /api/v1/meta/freshness (from
sync_runs). Add Redis caching for aggregates: key = hash(route+resolved_scope+params),
prefix agg:, TTL 12h (sync busts it). Add the per-user rate limiter (Redis sliding
window, 120/min; 429 with Retry-After). Integration tests per role using the RBAC
matrix fixtures."

──────────────────────────────────────────────────────────────────────────────
STEP 4 — FRONTEND SHELL  (run /clear first; new session)
──────────────────────────────────────────────────────────────────────────────

PROMPT 4.1:
"Read CLAUDE.md. Scaffold frontend/: Next.js 14 App Router + TS strict + Tailwind +
shadcn/ui. Firebase Auth (email/password) login page; authenticated layout with
sidebar nav (routes per the build order pages); typed API client with the error
envelope; TanStack Query provider; the global filter bar (date-range presets
7D/30D/90D/custom + compare toggle, platform, pod, publisher, app multi-selects
populated from /api/v1/apps) fully synced to URL search params; 'data as of' banner
from /meta/freshness; dark/light theme; skeleton loaders. No charts yet."

PROMPT 4.2:
"Add the ECharts foundation: lib/echarts.ts with tree-shaken imports (line, bar, pie,
heatmap, dataZoom, tooltip, brush), one theme file driving both modes, a typed
<Chart> wrapper with loading/empty/error states, and helpers for series formatting
(USD, %, compact numbers)."

──────────────────────────────────────────────────────────────────────────────
STEP 5 — PAGES (one prompt per page; /clear between pages if context grows)
──────────────────────────────────────────────────────────────────────────────

PROMPT 5.1: "Build the Executive Overview page exactly per docs spec §5.1: KPI cards
with vs-previous deltas from /metrics/summary; revenue-vs-spend line with profit
shading; revenue-composition stacked area; platform + pod splits; top-10 apps table
linking to /apps/[key]. All driven by the global filter bar."

PROMPT 5.2: "Build Revenue Analytics: HoU→Pod→App drill via chart click events,
IAP waterfall, AdMob-vs-AppLovin trend + eCPM, day-of-week heatmap."

PROMPT 5.3: "Build UA/Marketing: spend by network stacked, CPI + CTR per network,
spend-vs-revenue dual axis with break-even, CPI-vs-volume scatter. NO Adjust features."

PROMPT 5.4: "Build Store Performance: separated installs trends/shares,
organic_install_share, raw gp_uninstalls and apple_restores, paid-vs-organic mix table."

PROMPT 5.5: "Build Apps Explorer: TanStack Table + Virtual over /metrics/table —
permitted columns only (from /auth/me), sparkline cells, conditional formatting,
column picker, pinned app column, multi-sort, debounced search, row drawer."

PROMPT 5.6: "Build App Detail /apps/[canonical_key]: platform toggle, per-metric-group
chart blocks, metadata card. Handle 404-out-of-scope gracefully."

──────────────────────────────────────────────────────────────────────────────
STEP 6 — VIEWS, REPORTS, SHARING, EXPORTS
──────────────────────────────────────────────────────────────────────────────

PROMPT 6.1: "Backend: saved_views + saved_reports CRUD (columns validated against the
caller's permitted groups on write AND read), POST /reports/{id}/run executing through
the CALLER's RBAC, share request/approve/reject/revoke per CLAUDE.md rules, audit on
every transition. Tests: non-admin share is pending; admin auto-approved; recipient
with narrower scope sees only their rows/columns."

PROMPT 6.2: "Backend: POST /api/v1/export (capability-gated, 10/min limit) — csv
streamed, xlsx via openpyxl streamed, gsheet via Google Sheets API using per-user
OAuth consent; always server-side RBAC re-run + audit entry with exact filters."

PROMPT 6.3: "Frontend: saved-views UI in the filter bar; Reports page (builder with
group-by, permitted-column picker, filters, live preview; my reports; shared-with-me;
share dialog; export buttons honoring capabilities from /auth/me)."

──────────────────────────────────────────────────────────────────────────────
STEP 7 — ADMIN + DATA HEALTH
──────────────────────────────────────────────────────────────────────────────

PROMPT 7.1: "Backend admin routes per spec: users CRUD (Firebase invite), roles,
scope grants, per-role permission editing, pending-share approvals, audit query
(filter user/action/date, keyset), sync-runs list. Every route double-checks the
admin role server-side. Full tests."

PROMPT 7.2: "Frontend Admin Panel + Data Health pages per spec §5.8-5.9."

──────────────────────────────────────────────────────────────────────────────
STEP 8 — CI/CD + DEPLOY
──────────────────────────────────────────────────────────────────────────────

PROMPT 8.1: ".github/workflows/ci.yml: backend (ruff, mypy, pytest with Postgres+Redis
services, pip-audit) and frontend (eslint, tsc, tests, npm audit) — both block merge.
deploy-backend.yml → Cloud Run via Workload Identity Federation (no JSON keys).
Document Vercel setup + required env vars in docs/DEPLOY.md, including the
domain-swap-later checklist (CORS env + Firebase authorized domains + Vercel domain)."

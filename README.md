# Prometheus — Performance Dashboard

An enterprise analytics dashboard for mobile-app performance data, replacing a Looker
Studio dashboard for ~50 internal users. It turns the daily BigQuery performance feed into
a fast, role-aware web app: revenue, UA spend, installs, ad/IAP breakdowns, ROAS/CPI, and
profitability — with per-user row-level access control and a customizable Executive
Overview.

> **Project memory & locked decisions:** see [`CLAUDE.md`](./CLAUDE.md).
> **Local run (step-by-step):** [`docs/RUNBOOK-LOCAL.md`](./docs/RUNBOOK-LOCAL.md) ·
> **Production deploy:** [`docs/DEPLOY.md`](./docs/DEPLOY.md) ·
> **Design system:** [`docs/DESIGN.md`](./docs/DESIGN.md).

---

## 1. What it is

- **Audience:** ~50 internal users across roles (executives, pod owners, marketing,
  finance, analysts/viewers).
- **Purpose:** a single, governed analytics surface for mobile-app performance — the
  "Executive Overview" plus Revenue, UA, Store, Apps Explorer, and App Detail pages.
- **Why not Looker:** server-side RBAC down to the row, a faster purpose-built UI,
  saved views/reports with admin-approved sharing, exports, and an auditable trail.

---

## 2. Architecture

A **layered modular monolith** per tier (no microservices at this scale), cleanly split
backend ↔ frontend and serving ↔ analytics.

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 14 (App Router, TypeScript strict), Tailwind + shadcn/ui, Apache ECharts (tree-shaken, **lazy-loaded**), TanStack Table/Virtual/Query — deployed on **Vercel** |
| **Backend** | FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.0 async + Alembic — deployed on **Cloud Run** |
| **Serving DB** | **Neon** Postgres (serverless, **pooled**, TLS over the public internet) |
| **Cache** | **Upstash** Redis (serverless, TLS `rediss://`) — key prefix `agg:*`, busted by the daily sync |
| **Auth** | **Firebase Auth**; ID tokens verified server-side (`firebase-admin`) on every route |
| **Assistant** | Optional **ask-your-data** chatbot — Claude / ChatGPT / Gemini / Grok, whichever provider keys are set (see §3) |
| **Source** | **BigQuery** — the admin-set `bq_view` setting: a view **or** the raw `unified_daily_performance` table (the sync computes derived metrics itself, so a table works directly) |

### Data flow

```
BigQuery view (daily_performance_v1)
        │   daily sync: validate → staged load → integrity checks → UPSERT (history accumulates)
        ▼
Neon Postgres  (fact_daily_performance, dim_app, RBAC, audit, saved views/reports, layouts…)
        │   FastAPI (Cloud Run): RBAC + scoped SQL, results cached in Upstash Redis (agg:*)
        ▼
Next.js UI (Vercel)  ◄── Firebase ID token on every request
```

The API **never** queries BigQuery; users only ever read the materialized Postgres tables.

---

## 3. Key concepts

### Metric registry — single source of truth
`backend/app/core/metric_registry.py` (mirrored by `sync/metric_registry.py`) defines
**every fact column** (the curated registry — grown to include the reported `rpt_*` finance
ladder) and their metric groups. Generated from it: the Postgres fact DDL,
the per-role Pydantic response models, the RBAC column filters, and the fact indexes
(including the date covering index). A **drift guard** test
(`tests/test_metric_registry_parity.py`) fails CI if the two copies ever diverge in
columns/types/groups/order. **Never hand-write column lists elsewhere.** The curated
registry is still authoritative; columns an admin adopts from BigQuery at runtime (see
**Schema reconcile**) are carried alongside it as an `unclassified`, admin-only group.

### RBAC — enforced server-side
- **Roles:** `admin`, `executive`, `pod_owner`, `marketing`, `finance`, `viewer`.
- **Row scope:** `user_scopes(scope_type ∈ all|hou|pod|publisher|app, scope_value)`;
  effective access is the UNION of a user's rows. The scope is compiled to a SQL `WHERE`
  predicate and injected **first** in every query; client filters can only **narrow** it,
  never widen it (no-scope ⇒ no rows, fail-closed).
- **Metric scope:** `role_metric_permissions` (groups: store_installs, ua_spend,
  ad_revenue, iap_revenue, attribution, profitability — plus `unclassified`, granted to
  admins only for BigQuery-discovered columns) → forbidden columns are never serialized
  (per-role models from the registry).
- **Defense in depth:** the aggregate cache key varies by scope **and** permitted groups,
  so cached payloads never cross permission profiles; out-of-scope resources return **404**
  (indistinguishable from nonexistent). Frontend hiding is cosmetic only.

### Fail-safe sync job
`sync/sync_job.py` (the daily sync): record run → **validate** view schema vs the
registry → **staged load** (COPY into a staging table) → **integrity checks** (row delta
±30%, freshness ≤ 3 days, 7-day revenue penny-match vs BigQuery) → **UPSERT staging into the
live table** by natural key (`date, platform, app_key`) — re-running a date updates in place,
new dates append, aged-out history is retained → refresh `dim_app` → drop staging → bust
`agg:*`. On **any** failure it discards the staged data and leaves the live table untouched
(keeps serving existing data), alerts, and records the reason in `sync_runs`. The
dashboard never shows half-loaded data. The sync also loads the values of any
BigQuery-discovered dynamic columns (see below), so they aren't left NULL.

The **staging table has no primary key**, so a duplicate natural key `(date, platform,
app_key)` in the source view can never crash the load (the historical
`fact_daily_performance_staging_pkey` UniqueViolation). Before merging, staging is
de-duplicated on the natural key — keeping ONE deterministic row per key (highest revenue,
then installs) rather than double-counting — and the number removed is logged **and
alerted**, so a view anomaly is visible and fixable at the source. The **live** table keeps
its primary key, which the UPSERT relies on.

### Schema reconcile — "Match Database & BigQuery Schema"
When BigQuery's schema changes, admins can bring the Postgres serving layer into line
**without a redeploy** via a button in two places:
- **App Master page** (admin-only) → new BigQuery columns are added to the Postgres copy
  (read-only) and shown immediately.
- **Admin → Integration tab** (metrics fact table) → new BigQuery columns are adopted as
  the `unclassified` metric group and served to **admins only** — never to a non-admin role
  until an owner gives the column a curated metric group in the registry (a deliberate,
  RBAC-reviewed change). This keeps the who-can-see-what guarantee intact.

The reconcile is **additive and non-destructive**: it `ALTER … ADD COLUMN`s new columns
(guarded by a strict identifier pattern + a BigQuery→Postgres type allow-list; unsupported
types like STRUCT/ARRAY are skipped and reported), heals static registry columns missing
from Postgres, and **flags — never drops** — columns that vanish from BigQuery (the column
and its history are kept, marked inactive in `dynamic_columns`). Adopted columns live in the
`dynamic_columns` table; the effective registry refreshes on startup and on the request path
(TTL-guarded) so every worker converges within ~a minute. Both actions are audit-logged,
notify admins, and bust the aggregate cache. Engine: `app/services/schema_reconcile.py`
(+ `fact_schema.py` for the fact-table side).

### Ask-your-data assistant (chatbot)
A natural-language assistant ("what was total revenue last month?", "top 5 apps by ROAS")
that answers **only** from data the asking user is permitted to see. The user picks the model —
**Claude, ChatGPT, Gemini, or Grok** — from whichever providers have an API key configured.
RBAC is not bolted on: every model runs a tool-use loop whose tools execute through the
caller's scoped `QueryBuilder`, so there is **no text-to-SQL and no raw-SQL path**. The same
row-scope + metric-group limits apply identically for every provider, and hold even under
prompt injection (a jailbroken model has no out-of-scope data to reveal). Defense in depth: a
conservative input guardrail refuses obvious jailbreak / "reveal your prompt" / raw-SQL
attempts **before** any model call; the system prompt treats all message + tool content as
untrusted data; and every answer writes a **value-free forensic trace** (metric / dimension /
date window it touched — never the values) to the audit log. Off by default — needs the admin
`chat_enabled` setting **and** ≥1 provider key. Endpoints `POST /chat`, `GET /chat/status`;
engine `services/chat_service.py`, `chat_providers.py`, `chat_guardrails.py`.

### Proactive alerts, daily digest & scheduled reports
- **Anomaly alerts** (revenue drop, spend spike, low ROAS, stale data) evaluated once a day
  after the sync → in-app notifications to admins/execs + email.
- **Daily digest** email (opt-in): revenue, spend, profit, ROAS, top apps.
- **Scheduled report delivery**: email a saved report to yourself daily / weekly / monthly
  (CSV or XLSX). RBAC-safe — it always runs under the **owner's** access and is delivered
  **only** to the owner, so it can never leak data around RBAC.
- All three fire **exactly once cluster-wide** via a DB `job_runs` claim (no duplicate emails
  per instance or per restart). Mail is stdlib SMTP — a graceful no-op when unconfigured.

### Budget pacing & forecasting
- `GET /metrics/pacing` — month-to-date revenue vs the admin target, days elapsed, a linear
  month-end **projection**, attainment %, and on/off-pace — scoped to the caller (the revenue
  target is hidden from roles without revenue permission).
- `GET /metrics/forecast` — daily history plus an OLS linear-trend projection fit on
  **calendar-day offsets** (so gaps in the series don't skew the slope).

### Session security & 2FA
- Self-service **Security page**: whether this sign-in used **2FA** (from the token's
  second-factor claim), recent **device/activity**, and **"sign out of all devices"** —
  which stamps `users.sessions_revoked_at` (tokens issued earlier are rejected **live**) and
  best-effort revokes Firebase refresh tokens.
- **Admins** can force-sign-out any user.
- Optional `require_admin_2fa` setting gates admin actions behind a 2FA sign-in, with a
  **narrow break-glass** (only reading settings + toggling the requirement itself is exempt)
  so an admin can never lock themselves out.

### Observability
Every request gets a **trace id** (`X-Request-ID`, honored from the edge or generated) that
appears on every log line and in the error envelope (so a user can quote it to support);
**structured JSON logs** in production (`LOG_JSON`); optional **Sentry** error reporting
(env-gated, PII off). The frontend has route + global **error boundaries**. Engine
`core/observability.py`.

### App Master editing
The admin App Master page shows every `app_master_v2` column and allows editing exactly six —
`publisher`, `hou`, `pod_owner`, `pod`, `partner_name`, `net_revenue_share` — writing to
BigQuery first, then the Postgres copy, with full change history + undo. The edit drawer uses
**dropdowns** (pick an existing value or type a new one) for the categorical fields, and
**validates** `pod > 0` and `net_revenue_share ∈ [0.0, 1.0]` on both the client and the server.

---

## 4. Repository structure

```
backend/                 FastAPI service
  app/
    api/v1/              routes: auth, metrics, apps, meta, views, reports, export, admin, layouts
    core/               config, database, redis, cache, security, rate_limit, metric_registry, fact_table
    models/             SQLAlchemy ORM (identity, rbac, reports, layouts, settings, targets, dim, operations, dynamic_columns)
    schemas/            Pydantic request/response models
    services/           query_builder, auth, admin, reports, metrics, audit, settings, system, cache_warm, schema_reconcile, fact_schema, app_master
  alembic/              migrations (ORM-managed tables; the fact table is sync-owned)
  tests/                pytest suites (RBAC matrix, auth, cache, query builder, financial math, …)
  scripts/              seed_local.py (sample data), create_admin.py (link a Firebase UID → admin)
frontend/                Next.js app
  app/                  App Router pages: overview, revenue, ua, store, apps, data-health, admin, login
  components/           charts, tables, filters, layout, overview/, admin/, ui/ (shadcn)
  lib/                  api client + hooks, filters, formatting, echarts theme, overview layout
sync/                    daily BigQuery → Postgres job (sync_job.py) + its metric_registry copy
sql/                     bigquery/ (the contract view) + postgres/ (001 init, 002 fact, 003 targets)
docs/                    RUNBOOK-LOCAL, DEPLOY, DESIGN + the audit/review reports
design/                  visual reference (HTML mock, tokens.css, component map)
```

---

## 5. Local setup & run

**Prereqs:** Python 3.12, Node 20, and either Docker Desktop (Postgres + Redis in one
command) or free Neon + Upstash accounts. Full Windows walkthrough:
[`docs/RUNBOOK-LOCAL.md`](./docs/RUNBOOK-LOCAL.md).

Three terminals: **(0)** database + cache, **(1)** backend, **(2)** frontend.

### Required env vars (names only — never commit values)

| Where | Variables |
|---|---|
| `backend/.env` | `ENV`, `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS` |
| backend shell | `GOOGLE_APPLICATION_CREDENTIALS` (path to the Firebase Admin key, **outside** the repo) |
| backend (optional, prod) | `BIGQUERY_PROJECT`, `SYNC_TRIGGER_URL`, `SYNC_TRIGGER_TOKEN` |
| backend (optional — assistant) | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY` (a provider appears in the chat picker only when its key is set), `CHAT_MODEL` |
| backend (optional — email) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` (powers new-app alerts, the digest, and scheduled reports) |
| backend (optional — observability) | `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `LOG_LEVEL`, `LOG_JSON` |
| `frontend/.env.local` | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`, `NEXT_PUBLIC_SHOW_DEMO_WIDGETS` |
| `sync/.env` (real data) | `GCP_PROJECT`, `BQ_VIEW`, `PG_DSN`, `REDIS_URL`, `ALERT_WEBHOOK_URL` |

Each directory ships a `.env.example` (names only) — copy it and fill in your own values.
`NEXT_PUBLIC_*` are exposed to the browser by design (the Firebase web config is public);
**no server secret is ever a `NEXT_PUBLIC_*`**.

### (0) Database + cache
```bash
docker compose up -d        # Postgres on :5432, Redis on :6379
```

### (1) Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv/Scripts/activate
pip install ".[dev]"
cp .env.example .env                                  # set DATABASE_URL / REDIS_URL / CORS_ORIGINS
export GOOGLE_APPLICATION_CREDENTIALS="/path/outside/repo/firebase-admin.json"

alembic upgrade head                                  # create ORM tables + seed roles
PYTHONPATH=. python scripts/seed_local.py             # ~360 rows of sample fact data (no GCP)
PYTHONPATH=. python scripts/create_admin.py --uid <FIREBASE_UID> --email you@example.com

python -m uvicorn app.main:app --port 8000 --reload   # http://localhost:8000/health → {"status":"ok"}
```

### (2) Frontend
```bash
cd frontend
npm install
cp .env.example .env.local                            # set NEXT_PUBLIC_* (API base + Firebase web config)
npm run dev                                            # http://localhost:3000  (development)
# production-style:  npm run build && npm start
```

> **After every `git pull`:** re-run `pip install ".[dev]"` (new runtime deps land in the
> venv only on reinstall) and, in `frontend/`, `npm install`. If the UI behaves oddly or a
> build errors on stale chunks, **`rm -rf frontend/.next`** and rebuild. A **new** backend
> terminal forgets `GOOGLE_APPLICATION_CREDENTIALS` — re-`export` it before `uvicorn` or
> every login 401s.

---

## 6. Adding or changing a metric

Decide which kind first — the two paths touch different layers:

- **Derived / ratio metric** (ROAS, ad_roas, cpi*, *_ecpm, *_ctr, profit_usd,
  organic_install_share, totals like `total_revenue_usd = total_iap_net_usd +
  total_ad_revenue_usd`): compute it **in the BigQuery view**
  (`sql/bigquery/daily_performance_v1.sql`), **not** in Python or TypeScript. If the view
  exposes a new column, register it (next bullet).

- **New raw fact column:**
  1. Add **one `Col(...)` entry** to the registry — in **both**
     `backend/app/core/metric_registry.py` **and** `sync/metric_registry.py` (the parity
     test enforces they match), with its metric group.
  2. Add an **Alembic migration** for the column on the materialized fact table (the sync
     UPSERTs into the live table and no longer rebuilds it, so the column must exist there;
     the sync only creates the table from the registry on a fresh DB where it's absent).
  3. That's it — the registry **generates** the DDL, the per-role Pydantic models, the RBAC
     column filter, and the fact indexes. Don't hand-edit column lists anywhere.

Careful-change areas (review before touching): RBAC (scopes, response models,
`permitted_measures`), financial math, the metric registry + drift guard, the sync
pipeline, and auth.

---

## 7. Testing & security posture

**Backend tests** (real Postgres + Redis, fake Firebase verifier):
```bash
cd backend && source .venv/bin/activate
# point TEST_DATABASE_URL / REDIS_TEST_URL at a local Postgres + Redis (CI uses :5432/:6379)
pytest -q
```
Coverage includes the **RBAC matrix** (every role × representative endpoints), auth,
cache (incl. cross-role isolation), the query builder (scope-first, narrow-only,
keyset pagination), financial-ratio math (recomputed from totals, zero-denominator →
null), registry parity, layouts, the admin System tab, the **RBAC-safe chatbot** (both
provider loops, guardrails, forensic trace), **scheduled report delivery**, **pacing /
forecast**, and **session security / 2FA**. CI also runs `ruff`, `ruff format --check`, and
`mypy --strict`.

**Frontend tests** — Vitest + React Testing Library:
```bash
cd frontend && npm test
```
Cover the pure lib (formatting, filters, nav **RBAC gating**, XSS-escape) and feature/
RBAC visibility gating (e.g. the assistant widget only renders when enabled). The frontend
CI also runs `next lint`, `tsc --noEmit`, and `next build`.

**Security posture (summary).** Server-side RBAC on every route; row-scope injected into
SQL before data leaves the DB; fully parameterized queries with allow-listed
`group_by`/`sort`/`bucket`; permission-aware aggregate cache; least-privilege DB roles
(`api_service` has INSERT+SELECT only on the append-only `audit_log`; `sync_service` can't
touch RBAC tables); Bearer-token auth (no cookies ⇒ no CSRF); CORS locked to exact origins
(fails closed in prod); CSP/HSTS/`X-Frame-Options` headers; per-user rate limiting; input
caps on date range and filter lists; all sensitive actions audited. Standing security/
quality reviews (audit, red-team, cleanup, enterprise) are maintained for the project; the
main known open item is upgrading the Next.js dependency to a patched release.

---

## 8. Deployment

Backend → **Cloud Run**, frontend → **Vercel**, data → **Neon** + **Upstash**, auth →
**Firebase**. All secrets live in **GCP Secret Manager** (backend) or **Vercel env vars**
(frontend) — **never in the repo**. The daily sync runs as a **Cloud Run Job** on **Cloud
Scheduler**; an optional **Cloud Armor** WAF can front Cloud Run. Step-by-step (including
the env-var reference and a budget alert): [`docs/DEPLOY.md`](./docs/DEPLOY.md).

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Login worked, now **401 after restarting the backend** | A fresh terminal lost `GOOGLE_APPLICATION_CREDENTIALS`; re-`export` it before `uvicorn`. |
| Everything shows "—" / empty after a DB wipe | Re-seed (`scripts/seed_local.py`) and **re-crown your admin** (`scripts/create_admin.py --uid … --email …`) so your Firebase UID maps to an `admin` with `all` scope. The local seeder preserves existing admins, but a fresh DB needs this. |
| Stale data after a sync / want a clean cache | Clear the aggregate cache: `redis-cli FLUSHDB` (or delete `agg:*`). It also self-busts on each successful sync and expires at the daily boundary. |
| UI build errors / stale chunks after a pull | `rm -rf frontend/.next` then `npm install && npm run build`. |
| `ENOSPC` / out of disk during build | Free space: remove `frontend/.next` and `node_modules` (reinstall), prune Docker (`docker system prune`), clear caches. |
| CORS error in the browser | `CORS_ORIGINS` must be the **exact** frontend origin (e.g. `http://localhost:3000`); restart the backend. |
| Neon connection fails | Use the **pooled** host with the asyncpg driver and TLS: `postgresql+asyncpg://…?ssl=require`. |
| Upstash "Connection closed by server" | The Redis URL must be `rediss://` (TLS), not `redis://`. |
| `npm audit` warnings on install | Expected for dev; **do not** run `npm audit fix --force` (it breaks the build). |
| Sync fails: `UniqueViolation … fact_daily_performance_staging_pkey … (date, platform, app_key) already exists` | The BigQuery view emitted a **duplicate natural key**. Handled automatically now — staging has no PK and is de-duplicated before merge (kept-one is logged + alerted). If you see the old crash, the running sync image predates this fix; redeploy the latest `sync/`. Then investigate the view for the duplicated app/day. |
| App Master **"Refresh from BigQuery" → An unexpected error occurred** | Now returns a **sanitized 502** with the reason instead of a blind 500, and keeps existing data. Check the backend logs for the full `App Master refresh: serving-copy write failed` traceback — usually a value from BigQuery that doesn't fit a Postgres column type (e.g. a non-numeric `pod`). Fix the source row or the mapping, then refresh again. |
| "Run daily sync" → **Rate limit exceeded** | The heavy sync trigger is capped at 6/min (its own bucket). Read-only Test Connection / Check schema use a separate 20/min bucket, so they no longer starve it. Wait ~60s and click **once** — one run is all that's needed (an advisory lock prevents double-runs). |

---

*Secrets never belong in this repo. Use `.env*` files locally (gitignored) and Secret
Manager / Vercel env vars in production.*
</content>

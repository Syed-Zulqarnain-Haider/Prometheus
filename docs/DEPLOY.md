# DEPLOY.md — Production deployment (Cloud Run + Vercel)

This is the step-by-step for shipping Prometheus to production, reusing the same
**Neon (Postgres) + Upstash (Redis) + Firebase (Auth)** wiring proven locally
(see `docs/RUNBOOK-LOCAL.md`). Nothing here puts secrets in the repo — every secret
lives in **GCP Secret Manager** (backend) or **Vercel env vars** (frontend).

```
                 ┌────────────────────┐        ┌──────────────────────┐
  Browser  ──►   │  Vercel (Next.js)  │  ──►   │ Cloud Run (FastAPI)  │
                 │  frontend, HTTPS   │  CORS  │ uvicorn, HTTPS       │
                 └────────────────────┘        └──────────┬───────────┘
                          │ Firebase ID token             │
                          ▼                                ├─► Neon Postgres (TLS)
                 ┌────────────────────┐                    ├─► Upstash Redis (rediss://)
                 │  Firebase Auth     │ ◄── verify ────────┘
                 └────────────────────┘
        Daily: BigQuery view ─► Cloud Run Job (sync) ─► Neon  (see sync/)
```

---

## 0. Prerequisites

- A **GCP project** with billing enabled, and the `gcloud` CLI authenticated
  (`gcloud auth login && gcloud config set project <PROJECT_ID>`).
- A **Vercel** account connected to this GitHub repo.
- A **Neon** account (serverless Postgres) and an **Upstash** account (serverless Redis).
- A **Firebase** project (it can be the same GCP project) with **Email/Password**
  sign-in enabled.
- Enable the GCP APIs once:
  ```bash
  gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
      cloudbuild.googleapis.com secretmanager.googleapis.com
  ```

---

## 1. Provision the data services

### 1a. Neon Postgres
1. Create a Neon project → copy the **pooled** connection string.
2. Convert it to the async driver form the app expects:
   ```
   postgresql+asyncpg://<user>:<pass>@<host>/<db>?sslmode=require
   ```
   (TLS is mandatory — this is the accepted public-internet trade-off in CLAUDE.md.)
3. Apply the schema. The Postgres DDL lives in `sql/postgres/001_init.sql`,
   `002_fact_table.sql`, `003_revenue_targets.sql`; the app's own tables are also
   managed by Alembic. Run migrations with the **same container image** (§2d) or locally:
   ```bash
   cd backend && DATABASE_URL="postgresql+asyncpg://.../<db>?sslmode=require" alembic upgrade head
   ```

### 1b. Upstash Redis
1. Create an Upstash Redis database (pick the region closest to Cloud Run).
2. Copy the **`rediss://`** (TLS) URL — this becomes `REDIS_URL`.

### 1c. Firebase Auth
1. In the Firebase console, enable **Authentication → Email/Password**.
2. Under **Authentication → Settings → Authorized domains**, add your Vercel
   domain (e.g. `prometheus.vercel.app` and any custom domain).
3. Copy the web app config (apiKey, authDomain, projectId, appId) — these are the
   `NEXT_PUBLIC_FIREBASE_*` values (public by design, not secrets).
4. Provision the first admin user with `backend/scripts/create_admin.py` after the
   DB is migrated (see that script's `--help`).

---

## 2. Backend → Cloud Run

### 2a. Store secrets in Secret Manager (never in the repo)
```bash
printf '%s' 'postgresql+asyncpg://<user>:<pass>@<host>/<db>?sslmode=require' \
  | gcloud secrets create DATABASE_URL --data-file=-
printf '%s' 'rediss://<user>:<pass>@<host>:<port>' \
  | gcloud secrets create REDIS_URL --data-file=-
```
(Update later with `gcloud secrets versions add <NAME> --data-file=-`.)

### 2b. Build & push the image
The image is built from `backend/Dockerfile`, which `pip install`s straight from
`pyproject.toml` (single source of dependency truth, incl. `openpyxl` for XLSX export)
and serves `app.main:app` with uvicorn on `$PORT`.
```bash
cd backend
gcloud builds submit --tag <REGION>-docker.pkg.dev/<PROJECT_ID>/prometheus/api:latest .
```

### 2c. Deploy the service
```bash
gcloud run deploy prometheus-api \
  --image <REGION>-docker.pkg.dev/<PROJECT_ID>/prometheus/api:latest \
  --region <REGION> \
  --allow-unauthenticated \
  --min-instances 1 --max-instances 4 --concurrency 80 \
  --set-env-vars "ENV=production,GOOGLE_CLOUD_PROJECT=<FIREBASE_PROJECT_ID>,CORS_ORIGINS=https://<your-app>.vercel.app" \
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest"
```
Notes:
- `--allow-unauthenticated` lets the browser reach it; **auth is still enforced** —
  every route verifies a Firebase token (the `/health` liveness route is the only
  open endpoint).
- `ENV=production` turns on **HSTS** and the empty-CORS warning.
- Firebase token verification uses **Application Default Credentials** from the Cloud
  Run service account; `GOOGLE_CLOUD_PROJECT` pins the expected token audience.
- `--min-instances 1` avoids cold-start latency and keeps the in-process Redis-backed
  rate limiter warm.

### 2d. Run migrations (one-off, same image)
```bash
gcloud run jobs create prometheus-migrate \
  --image <REGION>-docker.pkg.dev/<PROJECT_ID>/prometheus/api:latest \
  --region <REGION> \
  --set-secrets "DATABASE_URL=DATABASE_URL:latest" \
  --command alembic --args upgrade,head
gcloud run jobs execute prometheus-migrate --region <REGION> --wait
```

---

## 3. Frontend → Vercel

1. **Import** the repo in Vercel; set **Root Directory** to `frontend`.
2. Add environment variables (Production + Preview):
   - `NEXT_PUBLIC_API_BASE_URL` = `https://prometheus-api-<hash>-<region>.run.app`
   - `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`,
     `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`
   - `NEXT_PUBLIC_SHOW_DEMO_WIDGETS` = `false`
3. Deploy. Vercel runs `next build` (same check CI runs on every PR).
4. **Close the loop**: set the backend's `CORS_ORIGINS` to the exact Vercel URL
   (re-run §2c or `gcloud run services update prometheus-api --set-env-vars CORS_ORIGINS=...`),
   and add the domain to Firebase **Authorized domains** (§1c).

---

## 4. Production hardening (what's already in the code)

- **Security headers** on every response (`app/core/security_headers.py`):
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  a locked-down `Content-Security-Policy` (`default-src 'none'; frame-ancestors 'none'`),
  COOP/CORP, `Permissions-Policy`, and **HSTS in production**.
- **CORS** is restricted to the exact origins in `CORS_ORIGINS` — never a wildcard.
  Empty origins in production are logged as an error.
- **Rate limiting** (`app/core/rate_limit.py`), per-user sliding window in Redis:
  **300/min general**, **10/min export**. Confirm/adjust the constants there if the
  team grows past ~50 users.
- **Error envelope**: clients only ever see `{"error": {"code", "message"}}` — no stack
  traces or SQL (`app/main.py` exception handlers).
- **Audit log** is append-only; the `api_service` DB role has no UPDATE/DELETE on it.

### Optional edge layer — Cloud Armor
For an extra WAF/DDoS tier, front Cloud Run with an external HTTPS Load Balancer and
attach a **Cloud Armor** policy (e.g. the preconfigured OWASP rules + a coarse
per-IP rate limit that complements the per-user app limit). This is optional for
~50 internal users; document the LB IP and lock Firebase authorized domains to it if used.

---

## 5. GCP budget alert (don't get surprised)

Create a budget with threshold alerts so cost overruns page you early:
```bash
# Find your billing account:
gcloud billing accounts list
# Create a $50/month budget alerting at 50/90/100% (adjust amount/recipients):
gcloud billing budgets create \
  --billing-account=<BILLING_ACCOUNT_ID> \
  --display-name="Prometheus monthly" \
  --budget-amount=50USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```
(Or set it in **Billing → Budgets & alerts** in the console.) Alerts e-mail the
billing admins; wire them to a channel if you prefer.

---

## 6. Environment variable reference

### Backend (Cloud Run) — secrets via Secret Manager, the rest via `--set-env-vars`
| Variable | Source | Example / notes |
|---|---|---|
| `DATABASE_URL` | **Secret** | `postgresql+asyncpg://…/<db>?sslmode=require` (Neon pooled) |
| `REDIS_URL` | **Secret** | `rediss://…` (Upstash, TLS) |
| `ENV` | env var | `production` (enables HSTS + CORS check) |
| `CORS_ORIGINS` | env var | exact Vercel origin(s), comma-separated, no wildcards |
| `GOOGLE_CLOUD_PROJECT` | env var | Firebase/GCP project id (token audience) |
| `PORT` | injected | set by Cloud Run; the image defaults to 8080 |

### Frontend (Vercel) — all public (`NEXT_PUBLIC_*`)
| Variable | Example / notes |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | the Cloud Run service URL |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase web config (public) |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | `…firebaseapp.com` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project id |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase web app id |
| `NEXT_PUBLIC_SHOW_DEMO_WIDGETS` | `false` in production |

---

## 7. CI / CD

- **CI** (`.github/workflows/ci.yml`) runs on every PR and on `main`:
  backend `ruff` + `mypy --strict` + `pytest` (against ephemeral Postgres/Redis
  service containers) and frontend `lint` + `tsc --noEmit` + `build`. Keep `main`
  green — the standing policy is squash-merge only when all checks pass.
- **CD** is intentionally manual (the `gcloud`/Vercel steps above). To automate later,
  add a deploy workflow gated on a `main` push that runs `gcloud run deploy` with a
  Workload-Identity-federated service account — no JSON keys in the repo.

---

## 8. Go-live checklist

- [ ] Migrations applied to Neon (`alembic upgrade head`).
- [ ] First admin user created (`scripts/create_admin.py`).
- [ ] Secrets in Secret Manager; **no** secret values committed anywhere.
- [ ] `CORS_ORIGINS` = exact Vercel domain; Firebase authorized domains updated.
- [ ] `ENV=production` (HSTS on); `/health` returns 200; a real login round-trips.
- [ ] XLSX export works (validates `openpyxl` is in the image).
- [ ] Budget alert active.

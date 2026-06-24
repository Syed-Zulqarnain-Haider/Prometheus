# DEPLOY-UBUNTU.md — single-VM production deploy (Ubuntu + Docker + nginx)

Run the whole stack on one Ubuntu server with `docker-compose.prod.yml`: the FastAPI
**backend**, the Next.js **frontend**, and **self-hosted Postgres + Redis** — all as
Docker containers — behind an **nginx** reverse proxy with **HTTPS**. Postgres and Redis
data persist in named Docker volumes. Both app containers bind to `127.0.0.1` only — nginx
is the only thing exposed to the internet.

> **Secrets never go in git.** `.env` and `secrets/` are gitignored. Use
> [`.env.production.example`](../.env.production.example) as the template.
> Architecture/decisions: [`CLAUDE.md`](../CLAUDE.md) · managed-cloud (Cloud Run + Vercel)
> alternative: [`DEPLOY.md`](./DEPLOY.md).
>
> Prefer **managed** Neon/Upstash instead of the bundled containers? Point `DATABASE_URL`,
> `SYNC_PG_DSN`, and `REDIS_URL` at them (TLS forms) and ignore the `db`/`redis` services.

```
            Internet ──443──► nginx (host) ──► / ───► 127.0.0.1:3000  (Next.js)
                                          └──► /api ► 127.0.0.1:8000  (FastAPI)
                                                          │
                                   db (Postgres, volume) ◄┘──► redis (volume)
                                   — all on the private compose network —
```

---

## 0. Before you start
- An Ubuntu 22.04/24.04 VM with a public IP and a domain name pointed at it (an `A`
  record → the VM's IP). Postgres + Redis run on the VM, so size it accordingly.
- A **Firebase** project with Email/Password (and/or Google) sign-in enabled, and an
  **Admin service-account key** JSON (used by the backend to verify tokens).
- **Optional (for real data):** a Google Cloud project with the BigQuery view and a
  **read-only** BigQuery service-account key (BigQuery Data Viewer + Job User) — a
  DIFFERENT identity from the Firebase key. Without it the dashboard runs fine but empty
  until the sync is wired (§12).

---

## 1. Server prep + firewall
```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install ufw git

# Only SSH and web ports are reachable from the internet; the app ports are NOT.
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'      # opens 80 + 443
sudo ufw --force enable
sudo ufw status
```

## 2. Install Docker (Engine + Compose plugin)
```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker     # run docker without sudo
docker compose version
```

## 3. Clone the repo
```bash
cd ~
git clone https://github.com/Syed-Zulqarnain-Haider/Prometheus.git
cd Prometheus
```

## 4. Secrets + environment (never committed)
```bash
# Service-account KEYS are files under ./secrets (mounted read-only into the backend):
mkdir -p secrets
#   Firebase Admin key (REQUIRED) — scp it up, e.g.:
#     scp firebase-admin.json user@server:~/Prometheus/secrets/
#   BigQuery READER key (OPTIONAL, for the sync — a DIFFERENT service account):
#     scp bq-reader.json      user@server:~/Prometheus/secrets/
chmod 600 secrets/*.json

# Environment from the template; fill in YOUR values:
cp .env.production.example .env
nano .env
chmod 600 .env
```
Set in `.env` (see the template's comments):
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` → the `db` container's credentials
  (choose a strong password). `PG_HOST_PORT` → host-only debug port (e.g. `5432`).
- `DATABASE_URL` → `postgresql+asyncpg://USER:PASSWORD@db:5432/DB` (matches the POSTGRES_* above).
- `SYNC_PG_DSN` → the same DB in **libpq** form `postgresql://USER:PASSWORD@db:5432/DB`
  (used by the sync subprocess; single-role deploy → same credentials).
- `REDIS_URL` → `redis://redis:6379/0` (in-network; no TLS needed).
- `CORS_ORIGINS` / `NEXT_PUBLIC_API_BASE_URL` → `https://your-domain` (exact, no trailing slash).
- `NEXT_PUBLIC_FIREBASE_*` → your Firebase **web** config (public).

> The BigQuery key PATH (`BQ_CREDENTIALS_PATH=/secrets/bq-reader.json`) is set in
> `docker-compose.prod.yml`, not `.env`. The non-secret sync settings (GCP project, view,
> schedule, on/off) are configured later in the app's **admin → Integration** tab, not here.

## 5. Build the images
```bash
docker compose -f docker-compose.prod.yml build
```
The frontend build inlines the `NEXT_PUBLIC_*` values from `.env` (public by design).

## 6. Create the database schema
The fact table must exist before the migrations that may alter it, so create it first,
then run the migrations — both via the backend image (no extra tooling). 6a creates
`fact_daily_performance` with its natural-key primary key `(date, platform, app_key)` —
the key the daily sync UPSERTs on (it accumulates history; it never swaps/replaces the
table). On this single-role deploy the DB superuser owns every table, so the sync's
writes and the Integration tab's **Clear Data** both work without extra grants.
```bash
# 6a. create the fact table (idempotent):
docker compose -f docker-compose.prod.yml run --rm -T backend python - <<'PY'
import asyncio
from app.core.database import engine
from app.core.fact_table import fact_metadata
async def main():
    async with engine.begin() as c:
        await c.run_sync(fact_metadata.create_all)
    await engine.dispose()
asyncio.run(main())
PY

# 6b. apply all ORM migrations (users, RBAC, saved views/reports, layouts, settings, …):
docker compose -f docker-compose.prod.yml run --rm -T backend alembic upgrade head
```

## 7. Start the stack
```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps      # both "running"
```
Quick check (loopback): `curl -s http://127.0.0.1:8000/health` → `{"status":"ok"}`.

## 8. Crown your first admin
Create the Firebase user in the Firebase console first, copy its **User UID**, then link
it to a DB admin (with an `all` row-scope):
```bash
docker compose -f docker-compose.prod.yml run --rm -T backend \
  python scripts/create_admin.py --uid <FIREBASE_UID> --email you@example.com
```
> **Do NOT run `scripts/seed_local.py` in production** — it writes sample fact data. Real
> data comes from the daily sync (§12). The dashboard works before the first sync; it just
> shows empty/"data as of —" until then.

## 9. nginx reverse proxy
```bash
sudo apt -y install nginx
sudo cp docs/nginx-prometheus.conf /etc/nginx/sites-available/prometheus
sudo ln -s /etc/nginx/sites-available/prometheus /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo sed -i 's/your-domain.example/YOUR_DOMAIN/' /etc/nginx/sites-available/prometheus
sudo nginx -t && sudo systemctl reload nginx
```

## 10. HTTPS with certbot
```bash
sudo apt -y install certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN          # adds the 443 server + HTTP→HTTPS redirect
sudo systemctl reload nginx
```
Certbot auto-renews via a systemd timer; check with `sudo certbot renew --dry-run`.

## 11. Verify
- Browse to `https://YOUR_DOMAIN` → you're redirected to the login page.
- Sign in with the Firebase user you crowned in §8 → the **Executive Overview** loads.
- `https://YOUR_DOMAIN/api/v1/meta/freshness` (while logged in) returns JSON.

## 12. Real data — the daily sync (managed from the Integration tab)
The backend runs the sync **itself** — an in-process scheduler plus on-demand controls in
the admin UI. No host cron, no separate job. You only need two things in place (both from
§4): the BigQuery reader key at `./secrets/bq-reader.json` and `SYNC_PG_DSN` set in `.env`.

Then, signed in as an admin, open **Admin → Integration** and:
1. **Connection health** confirms the BigQuery key is present and Postgres/Redis are up.
2. Set the **sync configuration** (stored in the DB, not env): GCP project, BigQuery view
   (e.g. `your_project.api.daily_performance_v1`), schedule time + IANA timezone.
3. **Test connection** runs a read-only BigQuery check; **Check schema** diffs the view's
   columns against the metric registry (informational only — never alters anything).
4. **Run sync now** kicks off a one-off load; or flip **Daily sync enabled** on and the
   in-process scheduler runs it once a day at your configured time. The run is guarded by a
   Postgres advisory lock, so even multiple backend instances fire it **exactly once/day**.

Each run validates the view against the registry, loads into a staging table, runs
integrity checks, then **UPSERTs** into the live table by `(date, platform, app_key)` —
history accumulates; on any failure the live data is untouched and the reason is recorded
in `sync_runs` (visible under **Sync history**). **Clear Data** (three confirmations + the
typed phrase `DELETE ALL DATA`) wipes ONLY the analytics tables (`fact_daily_performance`,
`dim_app`, `sync_runs`) — never users, roles, dashboards, settings, saved reports, or the
audit log.

> The sync's BigQuery client loads `BQ_CREDENTIALS_PATH` (`/secrets/bq-reader.json`)
> explicitly — a SEPARATE identity from the backend's Firebase `GOOGLE_APPLICATION_
> CREDENTIALS`. The two keys are never interchanged.

---

## 13. Day-2 operations
```bash
# Update to the latest code:
cd ~/Prometheus && git pull
docker compose -f docker-compose.prod.yml up -d --build      # rebuild + restart changed services
docker compose -f docker-compose.prod.yml run --rm -T backend alembic upgrade head   # if migrations changed

# Logs / status:
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.prod.yml ps

# Restart / stop:
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml down       # stop (data persists in the named volumes)
#   ⚠ `down -v` ALSO deletes the pgdata/redisdata volumes — only if you mean to wipe everything.

# Back up Postgres (the db container):
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > backup-$(date +%F).sql.gz

# Clear the aggregate cache (also self-busts on each successful sync, and on Clear Data):
docker compose -f docker-compose.prod.yml exec redis redis-cli FLUSHDB
```

## 14. Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad Gateway` from nginx | The backend/frontend container isn't up. `docker compose -f docker-compose.prod.yml ps` / `logs`. |
| Login works but API calls 404 | `NEXT_PUBLIC_API_BASE_URL` should be your bare domain (the app adds `/api/v1`); nginx `/api/` must have **no trailing slash** on `proxy_pass`. |
| Every login 401s | Backend can't verify tokens — check `secrets/firebase-admin.json` is mounted and the Firebase project matches; confirm `create_admin.py` used the **same UID**. |
| `alembic upgrade head` errors on a fresh DB | Run §6a (create the fact table) **before** §6b. |
| CORS error in the browser | `CORS_ORIGINS` in `.env` must equal your exact `https://` origin; `docker compose … up -d` to reload. |
| Backend can't reach the DB | `DATABASE_URL` host is `db` (the service name), form `postgresql+asyncpg://USER:PASSWORD@db:5432/DB`, with USER/PASSWORD/DB matching the `POSTGRES_*`. Check `docker compose … logs db`. |
| Sync fails immediately / "not configured" | Integration tab: the BigQuery key must be at `./secrets/bq-reader.json`, `SYNC_PG_DSN` set (libpq form, `@db:5432`), and the GCP project + view filled in. `Test connection` reports the cause without leaking secrets. |
| Redis errors | In-network `REDIS_URL=redis://redis:6379/0` (no TLS). Check `docker compose … logs redis`. (Managed Upstash instead → `rediss://`.) |
| `nginx -t`: duplicate `connection_upgrade` map | Your base nginx config already defines it — delete the `map` block at the top of `nginx-prometheus.conf`. |
| Out of disk during build | `docker system prune -af` and remove old images; ensure the VM has ≥ 10 GB free. |
| Need to roll back | `git checkout <previous-tag>` then `docker compose -f docker-compose.prod.yml up -d --build`. |

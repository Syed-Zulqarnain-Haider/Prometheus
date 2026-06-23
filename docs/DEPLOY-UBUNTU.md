# DEPLOY-UBUNTU.md — single-VM production deploy (Ubuntu + Docker + nginx)

Run the whole stack on one Ubuntu server: the FastAPI **backend** and the Next.js
**frontend** as Docker containers (via `docker-compose.prod.yml`), behind an **nginx**
reverse proxy with **HTTPS**. Data lives in **managed Neon Postgres + Upstash Redis**
(no DB/cache containers). Both app containers bind to `127.0.0.1` only — nginx is the
only thing exposed to the internet.

> **Secrets never go in git.** `.env` and `secrets/` are gitignored. Use
> [`.env.production.example`](../.env.production.example) as the template.
> Architecture/decisions: [`CLAUDE.md`](../CLAUDE.md) · managed-cloud (Cloud Run + Vercel)
> alternative: [`DEPLOY.md`](./DEPLOY.md).

```
            Internet ──443──► nginx (host) ──► / ───► 127.0.0.1:3000  (Next.js)
                                          └──► /api ► 127.0.0.1:8000  (FastAPI)
                                                          │
                                          Neon Postgres (TLS) ◄┘──► Upstash Redis (rediss://)
```

---

## 0. Before you start
- An Ubuntu 22.04/24.04 VM with a public IP and a domain name pointed at it (an `A`
  record → the VM's IP).
- A **Neon** project (pooled Postgres) and an **Upstash** Redis database.
- A **Firebase** project with Email/Password (and/or Google) sign-in enabled, and an
  **Admin service-account key** JSON (used by the backend to verify tokens).

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
# Firebase Admin key — copy your JSON to the server, then lock it down:
mkdir -p secrets
#   (scp it up, e.g.)  scp firebase-admin.json user@server:~/Prometheus/secrets/
chmod 600 secrets/firebase-admin.json

# Environment from the template; fill in YOUR values (Neon, Upstash, domain, Firebase web config):
cp .env.production.example .env
nano .env
chmod 600 .env
```
Set in `.env`:
- `DATABASE_URL` → your Neon **pooled** string, asyncpg form: `postgresql+asyncpg://…?ssl=require`
- `REDIS_URL` → your Upstash string, **`rediss://…`** (TLS)
- `CORS_ORIGINS` → `https://your-domain` (exact, no trailing slash)
- `NEXT_PUBLIC_API_BASE_URL` → `https://your-domain`
- `NEXT_PUBLIC_FIREBASE_*` → your Firebase **web** config (public)

## 5. Build the images
```bash
docker compose -f docker-compose.prod.yml build
```
The frontend build inlines the `NEXT_PUBLIC_*` values from `.env` (public by design).

## 6. Create the database schema
The sync-owned fact table must exist before the migrations that alter it, so create it
first, then run the migrations — both via the backend image (no extra tooling):
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

## 12. Real data — the daily sync (optional, when BigQuery is wired)
The sync job is vendored into the backend image, so it can run from the same container.
It needs its OWN BigQuery read-only key and a **libpq** Postgres DSN (`postgresql://…`,
not the asyncpg form). Run it manually first:
```bash
docker compose -f docker-compose.prod.yml run --rm -T \
  -v $HOME/Prometheus/secrets/bq-readonly.json:/secrets/bq.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/bq.json \
  -e GCP_PROJECT=<your_project> \
  -e BQ_VIEW=<your_project>.api.daily_performance_v1 \
  -e PG_DSN="postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require" \
  -e REDIS_URL="rediss://default:PASSWORD@HOST:PORT" \
  backend python sync/sync_job.py
```
On success it loads real rows and records a `success` in `sync_runs`; on failure it keeps
the previous data and records why. Schedule it daily with cron (host):
```bash
# crontab -e  — 06:00 UTC daily:
0 6 * * * cd $HOME/Prometheus && docker compose -f docker-compose.prod.yml run --rm -T \
  -v $HOME/Prometheus/secrets/bq-readonly.json:/secrets/bq.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/bq.json -e GCP_PROJECT=... -e BQ_VIEW=... \
  -e PG_DSN="postgresql://...?sslmode=require" -e REDIS_URL="rediss://..." \
  backend python sync/sync_job.py >> $HOME/prometheus-sync.log 2>&1
```

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
docker compose -f docker-compose.prod.yml down               # stop (data is in Neon/Upstash, safe)

# Clear the aggregate cache (also self-busts on each successful sync):
#   connect to Upstash with redis-cli (rediss) and FLUSHDB, or delete agg:* keys.
```

## 14. Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad Gateway` from nginx | The backend/frontend container isn't up. `docker compose -f docker-compose.prod.yml ps` / `logs`. |
| Login works but API calls 404 | `NEXT_PUBLIC_API_BASE_URL` should be your bare domain (the app adds `/api/v1`); nginx `/api/` must have **no trailing slash** on `proxy_pass`. |
| Every login 401s | Backend can't verify tokens — check `secrets/firebase-admin.json` is mounted and the Firebase project matches; confirm `create_admin.py` used the **same UID**. |
| `alembic upgrade head` errors on a fresh DB | Run §6a (create the fact table) **before** §6b. |
| CORS error in the browser | `CORS_ORIGINS` in `.env` must equal your exact `https://` origin; `docker compose … up -d` to reload. |
| Neon connection refused/TLS | DSN must be `postgresql+asyncpg://…?ssl=require` (pooled host). The sync's `PG_DSN` uses the libpq form `postgresql://…?sslmode=require`. |
| Upstash "Connection closed by server" | `REDIS_URL` must be `rediss://` (TLS), not `redis://`. |
| `nginx -t`: duplicate `connection_upgrade` map | Your base nginx config already defines it — delete the `map` block at the top of `nginx-prometheus.conf`. |
| Out of disk during build | `docker system prune -af` and remove old images; ensure the VM has ≥ 10 GB free. |
| Need to roll back | `git checkout <previous-tag>` then `docker compose -f docker-compose.prod.yml up -d --build`. |

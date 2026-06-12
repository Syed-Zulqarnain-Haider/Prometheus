# RUNBOOK-LOCAL.md — Run the full stack on a Windows laptop

Audience: the owner (not a developer). Goal: see the **Executive Overview** working
on your own machine, the simplest way. Everything is copy‑paste. You'll use **Git
Bash** (the terminal that came with Git) for every command.

There are two choices you'll make:
- **Database + cache:** the simplest path uses **Docker Desktop** (one command brings
  up Postgres + Redis). If you'd rather not install Docker, there's a no‑Docker path
  using free cloud services (Neon + Upstash). Docker is recommended.
- **Data:** the simplest path **seeds sample data** (no Google Cloud needed). The real
  data path (BigQuery) is optional and at the end.

Estimated time: ~30–45 minutes the first time.

> Throughout, replace `you@example.com` etc. with your real values. Anywhere you see
> `C:/Users/you/...`, use your real Windows path **with forward slashes**.

---

## 0. What you'll end up with
- A backend API at **http://localhost:8000**
- The dashboard at **http://localhost:3000**
- A login with your email/password, landing on a populated Overview.

---

## 1. Install the basics (one time)

Install these by downloading the installers and clicking through (defaults are fine).
On the Python and Node installers, if asked, **leave "Add to PATH" checked**.

1. **Git** (you already have it if you have Git Bash). https://git-scm.com/download/win
2. **Python 3.12** — https://www.python.org/downloads/windows/ → "Windows installer
   (64‑bit)". On the first screen **tick "Add python.exe to PATH"**, then "Install Now".
3. **Node.js 20 LTS** — https://nodejs.org/ → the **LTS** button.
4. **Docker Desktop** (recommended) — https://www.docker.com/products/docker-desktop/
   Install, launch it once, and wait until it says "Engine running".
   *(Skip if you're doing the no‑Docker path in §3B.)*

Open **Git Bash** and check the versions (each should print a number):

```bash
git --version
python --version      # 3.12.x
node --version        # v20.x
docker --version      # only if you installed Docker
```

> If `python --version` says "command not found", use the Windows launcher instead:
> run `py -3.12 --version`, and wherever this guide says `python`, use `py -3.12`
> (e.g. `py -3.12 -m venv .venv`).

---

## 2. Get the code

Pick a folder, then clone (skip if you already have the repo):

```bash
cd ~
git clone https://github.com/Syed-Zulqarnain-Haider/Prometheus.git
cd Prometheus
```

---

## 3. Database + cache (pick ONE: A or B)

### 3A. Docker (recommended — one command)

From the repo root, with Docker Desktop running:

```bash
docker compose up -d
```

This starts Postgres on `localhost:5432` and Redis on `localhost:6379`. Check:

```bash
docker compose ps        # both should say "running"/"healthy"
```

Your connection values for later:
- `DATABASE_URL = postgresql+asyncpg://prometheus:prometheus@localhost:5432/prometheus`
- `REDIS_URL    = redis://localhost:6379/0`

### 3B. No Docker (free cloud Postgres + Redis)

1. **Postgres on Neon** — sign up at https://neon.tech (free). Create a project; in
   "Connection Details" copy the connection string. Convert it to our format:
   `postgresql+asyncpg://USER:PASSWORD@HOST/DBNAME?ssl=require`
   (start from Neon's string, put `+asyncpg` after `postgresql`, and end with
   `?ssl=require`). That's your `DATABASE_URL`.
2. **Redis on Upstash** — sign up at https://upstash.com (free). Create a Redis
   database; copy the connection URL (not the REST one). **It must start with
   `rediss://`** (two s's — that's the TLS/secure form Upstash requires). If you paste
   a plain `redis://` URL the backend fails with "Connection closed by server"; just
   change `redis://` to `rediss://`. That's your `REDIS_URL`.

---

## 4. Firebase (login + your admin user)

The dashboard signs you in with Firebase. You need two things from Firebase: the
**web config** (safe, goes in the frontend) and an **Admin service‑account key**
(secret, lives **outside** the repo, used by the backend to verify logins).

1. Go to https://console.firebase.google.com → **Add project** (any name) → create.
2. **Enable email/password login:** left menu **Build → Authentication → Get started →
   Sign‑in method → Email/Password → Enable → Save**.
3. **Create your user:** Authentication → **Users → Add user** → enter your email +
   a password → Add. Then **copy that user's "User UID"** (the long string in the
   row) — you'll need it in §6.
4. **Get the web config:** gear icon **Project settings → General →** scroll to
   "Your apps" → click the **`</>` (Web)** icon → register an app (any nickname) →
   you'll see a `firebaseConfig` block. Keep these four values handy:
   `apiKey`, `authDomain`, `projectId`, `appId`.
5. **Get the Admin key (secret):** Project settings → **Service accounts →
   Generate new private key → Generate key**. A `.json` file downloads. **Move it
   OUTSIDE the repo**, e.g. to `C:/Users/you/keys/prometheus-admin.json`.
   **Never put this file in the project folder or commit it.**
   > ⚠️ **Windows hides known extensions.** If "File name extensions" is off in
   > File Explorer and you rename the file, you can end up with a hidden double
   > extension like `prometheus-admin.json.json`. The backend then can't find the
   > key and **every login fails with 401**. Turn on **View → File name extensions**
   > and confirm the file is exactly `…admin.json` (one `.json`).

---

## 5. Start the backend (Terminal 1)

In Git Bash:

```bash
cd ~/Prometheus/backend

# one‑time Python setup
python -m venv .venv
source .venv/Scripts/activate          # note: Scripts (Windows), not bin
pip install ".[dev]"

# configuration
cp .env.example .env
```

Open `backend/.env` in Notepad and set these three lines (use your §3 values):

```
DATABASE_URL=postgresql+asyncpg://prometheus:prometheus@localhost:5432/prometheus
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:3000
```

Back in Git Bash, point the backend at your Firebase Admin key (use YOUR path), then
create the tables and seed sample data:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="C:/Users/you/keys/prometheus-admin.json"

alembic upgrade head                      # create tables + seed roles
PYTHONPATH=. python scripts/seed_local.py # ~360 rows of sample data (no Google Cloud)
```

Now make yourself an admin (use the **User UID** you copied in §4‑3):

```bash
PYTHONPATH=. python scripts/create_admin.py --uid PASTE_FIREBASE_UID --email you@example.com
```

Start the API (leave this terminal running):

```bash
uvicorn app.main:app --port 8000 --reload
```

Leave it. It should say "Application startup complete". Quick check in a browser:
**http://localhost:8000/health** → `{"status":"ok"}`.

> If you used the **no‑Docker** path, the same commands apply — just make sure
> `DATABASE_URL`/`REDIS_URL` in `.env` are your Neon/Upstash values.

---

## 6. Start the frontend (Terminal 2)

Open a **second** Git Bash window:

```bash
cd ~/Prometheus/frontend
npm install
cp .env.example .env.local
```

> `npm install` may print a few "vulnerabilities" notices — that's normal for a dev
> setup. **Do NOT run `npm audit fix --force`** (npm even suggests it): the `--force`
> flag upgrades packages across major versions and will break the build. Ignore it.

Open `frontend/.env.local` in Notepad and fill in the **web config** from §4‑4:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_FIREBASE_API_KEY=...your apiKey...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=...your authDomain...
NEXT_PUBLIC_FIREBASE_PROJECT_ID=...your projectId...
NEXT_PUBLIC_FIREBASE_APP_ID=...your appId...
NEXT_PUBLIC_SHOW_DEMO_WIDGETS=false
```

Start it (leave running):

```bash
npm run dev
```

Open **http://localhost:3000** → you'll be sent to the login page. Sign in with the
email + password you created in §4‑3.

---

## 7. Verification checklist — what you should see

On the **Executive Overview** after login:

- ✅ Top strip: **"Data as of …"** with a green **success** badge (from the sample sync).
- ✅ **Five KPI cards** — Revenue, Spend, Net IAP, Profit, Profit % — each with a
  number, a small ▲/▼ change, and a tiny sparkline.
- ✅ **Revenue Progress** donut shows **"Target not set"** (correct — targets come in a
  later step; it is honest, not a fake number).
- ✅ **Monthly Revenue Trend** bars.
- ✅ **Revenue vs Spend** chart (two lines, shaded profit) and **Revenue Composition**
  (stacked area).
- ✅ **ROAS / Ad ROAS / CPI** ratio cards with values.
- ✅ **Revenue by Platform** and **Revenue by Pod** donuts.
- ✅ **Publisher Performance** and **Top Apps by Revenue** tables; clicking an app name
  opens its detail page.
- ✅ Change the date preset (7D/30D/90D) or toggle **Compare** in the top bar — the page
  updates and the **URL changes** (you can copy/share that URL).
- ✅ Toggle the **theme** (sun/moon, top‑right) — the whole UI switches paper/night.

If you see all of that, the full stack is working end‑to‑end. 🎉

To switch the demo‑only widgets on later, set `NEXT_PUBLIC_SHOW_DEMO_WIDGETS=true` in
`frontend/.env.local` and restart `npm run dev` — they'll appear with a **DEMO DATA**
badge.

---

## 8. Stopping / restarting

- Stop a server: click its Git Bash window and press **Ctrl+C**.
- Stop the database/cache: `docker compose down` (add `-v` to also wipe the data).

### Restarting the backend properly (important)

A **new** Git Bash window forgets the virtual environment **and** the
`GOOGLE_APPLICATION_CREDENTIALS` setting. If you just run `uvicorn …` in a fresh
window, the server starts but **login silently fails (401)** because it can no longer
verify Firebase tokens. Always run the **full four steps** in the backend window:

```bash
cd ~/Prometheus/backend
source .venv/Scripts/activate
export GOOGLE_APPLICATION_CREDENTIALS="C:/Users/you/keys/prometheus-admin.json"
uvicorn app.main:app --port 8000 --reload
```

So a normal next-time startup is: `docker compose up -d` (if you use Docker) → the
four backend steps above → in the frontend window `npm run dev`. You only re-run
`alembic upgrade head` / the seed scripts if you wiped the database.

---

## 9. Common hiccups

| Symptom | Fix |
|---|---|
| Login spins / "Failed to fetch" | Backend not running, or `NEXT_PUBLIC_API_BASE_URL` wrong. Confirm http://localhost:8000/health. |
| Login rejected for a real user | The backend can't verify the token — check `GOOGLE_APPLICATION_CREDENTIALS` points to your Admin JSON (forward slashes), and that you ran `create_admin.py` with the **same UID** as the Firebase user. |
| Page loads but everything says "—" / empty | You're logged in as a non‑admin, or seeding didn't run. Re‑run `scripts/seed_local.py` and `scripts/create_admin.py`. |
| CORS error in the browser console | `CORS_ORIGINS` in `backend/.env` must be exactly `http://localhost:3000`. Restart the backend. |
| `source .venv/bin/activate` not found | On Windows it's `source .venv/Scripts/activate`. |
| `python` not found | Use the launcher: `py -3.12` (e.g. `py -3.12 -m venv .venv`). |
| Neon connection fails | Ensure the URL is `postgresql+asyncpg://…?ssl=require` (with `+asyncpg` and `?ssl=require`). |
| Upstash "Connection closed by server" | The Redis URL must be `rediss://` (TLS), not `redis://`. |
| Login worked, now 401 after restarting | New window lost `GOOGLE_APPLICATION_CREDENTIALS`. Re‑`export` it before `uvicorn` (see §8). |
| 401 even with the right UID | The key file may be `…json.json` (hidden double extension). Turn on File name extensions and rename to a single `.json`. |
| `create_admin.py` errors with "UniqueViolation" | Fixed — re‑pull. The script now updates the existing email's UID instead of crashing. |
| npm "vulnerabilities" warning | Normal — **do not** run `npm audit fix --force` (it breaks the build). |

---

## 10. (Advanced, optional) Real data from BigQuery

Only do this once the sample‑data run works, and only if your BigQuery project already
holds the underlying performance table. This needs Google Cloud access.

1. **Create the `api` dataset** in your project (BigQuery console → your project →
   Create dataset → ID `api`).
2. **Create the contract view:** open `sql/bigquery/daily_performance_v1.sql`, change
   the project/dataset names to **yours** (it ships pointing at `terafort.*`), and run
   it in the BigQuery console. It builds `your_project.api.daily_performance_v1`.
3. **Read‑only credentials:** create a service account, grant it
   **BigQuery Data Viewer** on the `api` dataset and **BigQuery Job User** on the
   project, and download its JSON key to **outside the repo** (never commit it).
4. **Run the sync once** (Terminal 3):
   ```bash
   cd ~/Prometheus/sync
   python -m venv .venv && source .venv/Scripts/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
   Edit `sync/.env`:
   ```
   GCP_PROJECT=your_project
   BQ_VIEW=your_project.api.daily_performance_v1
   PG_DSN=postgresql://prometheus:prometheus@localhost:5432/prometheus
   REDIS_URL=redis://localhost:6379/0
   ```
   Then:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="C:/Users/you/keys/prometheus-bq-readonly.json"
   python sync_job.py
   ```
   On success it loads real rows into Postgres and records a `success` in `sync_runs`;
   the Overview now shows your real numbers. On failure it keeps the previous data and
   records why — the dashboard never shows half‑loaded data.

> The sample‑data seeder (`scripts/seed_local.py`) and the real sync write to the same
> `fact_daily_performance` table, so you can always fall back to sample data by
> re‑running the seeder.

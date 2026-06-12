# Prometheus Backend (FastAPI)

Step 2 scaffold: app entrypoint, config, SQLAlchemy models mirroring
`sql/postgres/001_init.sql`, and an Alembic baseline. Business logic (auth, RBAC,
metrics API) is added in later build steps.

## Local development

```bash
# 1. Start Postgres + Redis (from repo root)
docker compose up -d

# 2. Backend setup
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # or: pip install ".[dev]"
cp .env.example .env             # adjust if needed

# 3. Create the schema
alembic upgrade head

# 4. Run the API
uvicorn app.main:app --reload    # GET http://localhost:8000/health -> {"status":"ok"}
```

## Quality gates

```bash
ruff check . && ruff format --check .
mypy app
pytest -q
```

## Notes

- `DATABASE_URL` uses the async driver: `postgresql+asyncpg://...`.
- The sync-owned `fact_daily_performance` table (see `sql/postgres/002_fact_table.sql`)
  is **not** modeled by the ORM and is excluded from Alembic autogenerate.
- The least-privilege DB roles (`api_service`, `sync_service`) and their GRANTs are a
  production deploy concern (applied via `001_init.sql` on Cloud SQL), not Alembic.
- Production secrets come from GCP Secret Manager — never a committed `.env`.

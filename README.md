# Step 1 — Data Foundation (BigQuery view → Sync job → PostgreSQL)

## What this is
The complete, tested data pipeline foundation for the Terafort dashboard:
- `sql/bigquery/daily_performance_v1.sql` — the stable contract view (run once in BigQuery; re-run only to evolve it while keeping output columns stable)
- `sql/postgres/001_init.sql` — RBAC, scopes, saved views/reports, admin-approval sharing, append-only audit log, sync state, role seeds, least-privilege DB roles
- `sql/postgres/002_fact_table.sql` — GENERATED from the metric registry (do not hand-edit)
- `sync/metric_registry.py` — single source of truth for all 78 columns; drives DDL, schema validation, and later the API's RBAC column filters
- `sync/sync_job.py` — the daily Cloud Run Job: validate schema → staged load → integrity checks (row delta ±30%, freshness ≤3 days, 7-day revenue penny-match) → atomic swap → dim_app refresh → Redis cache bust. On ANY failure: yesterday's data keeps serving, alert fires, sync_runs records why.

## Deploy order
1. **BigQuery**: `CREATE SCHEMA IF NOT EXISTS terafort.api;` then run `daily_performance_v1.sql`.
2. **Service account** `dashboard-sync@<project>`: `roles/bigquery.dataViewer` on the `api` dataset ONLY + `roles/bigquery.jobUser` on the project.
3. **Cloud SQL** (Postgres 15+, private IP, SSL required): run `001_init.sql` then `002_fact_table.sql` as the admin user; set passwords for `api_service` / `sync_service` and store in Secret Manager.
4. **Build & deploy the job**:
   ```
   gcloud builds submit sync/ --tag <region>-docker.pkg.dev/<project>/dash/sync:v1
   gcloud run jobs create dashboard-sync --image ... \
     --set-env-vars GCP_PROJECT=...,BQ_VIEW=terafort.api.daily_performance_v1 \
     --set-secrets PG_DSN=pg-dsn-sync:latest,REDIS_URL=redis-url:latest \
     --vpc-connector <connector> --service-account dashboard-sync@... \
     --max-retries 3 --task-timeout 30m
   ```
5. **Cloud Scheduler**: trigger the job daily at 06:00 UTC (after the 05:16 UTC table rebuild).
6. Run the job once manually; verify `SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1;` shows `success` and `bq_built_at` is fresh.

## Validation performed (in this delivery)
- Both DDL files executed clean on PostgreSQL with ON_ERROR_STOP
- Role seeds verified: admin/executive/pod_owner = 6 metric groups, marketing/finance = 5 (marketing includes IAP per owner decision), viewer = 1
- Generated `app_key` PK tested with real sample-row data; duplicate rejection confirmed
- `user_scopes` CHECK constraint confirmed (rejects `'all'` with a value)
- Atomic swap executed 3 consecutive times — no index/constraint name collisions
- Python compile-checked; registry uniqueness asserted (78 columns, no duplicates)

## Not yet validated (requires your GCP project)
- Live BigQuery connectivity & IAM — first manual job run will prove it
- Cloud Run/Scheduler wiring — follow step 4–5 above

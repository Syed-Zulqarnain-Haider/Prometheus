"""Application configuration.

All settings — and especially every secret — are loaded from the environment
(or a local ``.env`` for development). No secret values are ever hard-coded here;
see CLAUDE.md security rules. ``.env.example`` documents the expected variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, validated at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    env: str = "development"
    project_name: str = "Prometheus API"
    api_v1_prefix: str = "/api/v1"

    # Connections (database_url is required — a misconfigured deploy fails fast).
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Data-source / sync wiring (operational, env-only — NEVER stored in the DB or
    # shown in the UI). Their PRESENCE drives the System tab's BigQuery status and the
    # "Run sync now" trigger; absence (local/seed) means "not configured".
    bigquery_project: str | None = None
    sync_trigger_url: str | None = None  # e.g. the deployed Cloud Run Job execution URL
    sync_trigger_token: str | None = None  # bearer for the trigger URL (secret; env only)

    # Path to the BigQuery READER service-account key. This is a SEPARATE identity from
    # Firebase's GOOGLE_APPLICATION_CREDENTIALS — never reuse that one for BigQuery. The
    # key is a MOUNTED FILE (never uploaded or stored via the UI/DB); only its PATH is
    # configured here. Its presence drives the Integration tab's BigQuery status, and the
    # read-only "Test Connection" loads it explicitly from this path.
    bq_credentials_path: str = "/secrets/bq-reader.json"

    # Path to the BigQuery WRITER key — a service account with BigQuery Data Editor on the
    # app_master dataset, a SEPARATE identity from the read-only reader above. Mounted file;
    # only its PATH is configured here (never uploaded/stored via UI/DB). Required ONLY for
    # admin App Master edits (write-back to BigQuery); absent -> edits return a clear
    # "BigQuery write-back not configured" error and nothing is changed.
    bq_writer_credentials_path: str = "/secrets/bq-writer.json"

    # NOTE: the App Master BigQuery table id is NOT an env var — it's the admin-editable,
    # DB-backed ``app_master_bq_table`` setting (Integration tab), so it can be changed at
    # runtime without a redeploy. See app/core/settings_registry.py.

    # libpq DSN the sync uses to write Postgres, e.g.
    # postgresql://sync_service:...@host:5432/db?sslmode=require. This is the SYNC's DB
    # identity (the write-capable ``sync_service`` role) — DISTINCT from ``database_url``
    # (the api's read role). Secret, env-only (never DB/UI/logs). Its presence (plus the
    # BQ key + GCP project) is what enables the backend to run the sync LOCALLY; absent,
    # the scheduler/trigger falls back to ``sync_trigger_url`` or reports not-configured.
    sync_pg_dsn: str | None = None

    # SMTP for admin email alerts (e.g. a new app discovered on refresh). Operational,
    # env-only — the password is a SECRET (Secret Manager / env, never DB/UI/logs). Email is
    # "configured" only when smtp_host AND smtp_from are set; otherwise every send is a
    # graceful no-op (logged) and the in-app notification still fires. Set smtp_password for
    # authenticated relays; leave empty for an open internal relay.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    # "Ask your data" assistant (chatbot). The API key is a SECRET — env / Secret Manager
    # only, NEVER stored in the DB or shown in the UI. Its PRESENCE (plus the admin
    # ``chat_enabled`` operational setting) is what makes the assistant available; absent,
    # the endpoint returns a clean "not configured" and the UI hides the widget. The
    # assistant only ever reads data through the caller's scoped QueryBuilder — it cannot
    # see anything the user could not see themselves, and it never generates SQL.
    anthropic_api_key: str | None = None
    chat_model: str = "claude-opus-5"
    # Bound on the tool-use loop (each iteration is one model call that may run tools) and
    # the answer length — caps the per-question cost of a hostile or runaway question.
    chat_max_iterations: int = 6
    chat_max_tokens: int = 2048

    # Exact frontend origins, comma-separated (kept as a raw string so
    # pydantic-settings does not attempt to JSON-decode it). Use cors_origin_list.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed list of exact CORS origins (never wildcards)."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (values sourced from the environment)."""
    return Settings()

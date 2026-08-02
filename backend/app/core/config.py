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

    # "Ask your data" assistant (chatbot). Every provider API key is a SECRET — env /
    # Secret Manager only, NEVER stored in the DB or shown in the UI. A provider is
    # "available" iff its key is set; the admin ``chat_enabled`` setting gates the feature
    # overall. WHICHEVER provider the user picks, the assistant only ever reads data through
    # the caller's scoped QueryBuilder — it cannot see anything the user could not see
    # themselves, and it never generates SQL. The security boundary is provider-agnostic.
    #
    # Claude (Anthropic SDK):
    anthropic_api_key: str | None = None
    chat_model: str = "claude-opus-5"
    # OpenAI / ChatGPT, and the two OpenAI-compatible providers below (xAI Grok + Google
    # Gemini via its OpenAI-compat endpoint). Model ids are env-overridable because
    # third-party model names change independently of this app — set them per deployment.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    xai_api_key: str | None = None
    grok_model: str = "grok-2-latest"
    # Bound on the tool-use loop (each iteration is one model call that may run tools) and
    # the answer length — caps the per-question cost of a hostile or runaway question.
    chat_max_iterations: int = 6
    chat_max_tokens: int = 2048

    # Observability. SENTRY_DSN is a SECRET (env/Secret Manager only). Absent → Sentry stays
    # off and the app still emits structured, trace-correlated logs. log_json defaults on in
    # non-development so log aggregators get one JSON object per line; locally it's plain text.
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0
    log_level: str = "INFO"
    log_json: bool = False

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

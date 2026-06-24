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

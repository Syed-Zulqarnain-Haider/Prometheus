"""Test configuration and fixtures.

Sets safe placeholder env vars BEFORE the app/config modules are imported, then
provides an integration test harness for the auth routes: a real Postgres test
database (schema + seed data), a fake Redis cache, and a fake token verifier
(no network / no real Firebase project).
"""

import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ENV", "test")

TEST_DATABASE_URL = os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://prometheus:prometheus@127.0.0.1:55432/prometheus_test",
)

import pytest_asyncio  # noqa: E402
from app.models import Base  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

# ── Known test identities (firebase_uid) ────────────────────────────────────
ACTIVE_UID = "active-uid-123"
INACTIVE_UID = "inactive-uid-456"
UNKNOWN_UID = "ghost-uid-789"
ACTIVE_USER_ID = "11111111-1111-1111-1111-111111111111"
INACTIVE_USER_ID = "22222222-2222-2222-2222-222222222222"

# Tokens accepted by the fake verifier; anything else is "malformed".
TOKEN_MAP: dict[str, dict[str, Any]] = {
    "valid-active": {"uid": ACTIVE_UID},
    "valid-inactive": {"uid": INACTIVE_UID},
    "valid-unknown": {"uid": UNKNOWN_UID},
}

# ── Seed SQL (roles/permissions/capabilities mirror 001_init.sql) ────────────
SEED_ROLES = (
    "INSERT INTO roles (name) VALUES "
    "('admin'),('executive'),('pod_owner'),('marketing'),('finance'),('viewer');"
)
SEED_PERMS = """
INSERT INTO role_metric_permissions (role_id, metric_group)
SELECT r.id, g.g FROM roles r
JOIN LATERAL (SELECT unnest(CASE r.name
  WHEN 'admin'     THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']
  WHEN 'executive' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']
  WHEN 'pod_owner' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','attribution','profitability']
  WHEN 'marketing' THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','profitability']
  WHEN 'finance'   THEN ARRAY['store_installs','ua_spend','ad_revenue','iap_revenue','profitability']
  WHEN 'viewer'    THEN ARRAY['store_installs']
END) AS g) g ON true;
"""
SEED_CAPS = """
INSERT INTO role_capabilities (role_id, capability)
SELECT r.id, c.c FROM roles r
JOIN LATERAL (SELECT unnest(CASE r.name
  WHEN 'admin'     THEN ARRAY['export','share_report','admin_panel']
  WHEN 'executive' THEN ARRAY['export','share_report']
  WHEN 'pod_owner' THEN ARRAY['export','share_report']
  WHEN 'marketing' THEN ARRAY['export','share_report']
  WHEN 'finance'   THEN ARRAY['export','share_report']
  ELSE ARRAY[]::text[]
END) AS c) c ON true;
"""
SEED_USERS = f"""
INSERT INTO users (id, firebase_uid, email, display_name, is_active) VALUES
  ('{ACTIVE_USER_ID}','{ACTIVE_UID}','active@terafort.org','Active User', true),
  ('{INACTIVE_USER_ID}','{INACTIVE_UID}','inactive@terafort.org','Inactive User', false);
"""
SEED_USER_ROLES = (
    f"INSERT INTO user_roles (user_id, role_id) "
    f"SELECT '{ACTIVE_USER_ID}', id FROM roles WHERE name='marketing';"
)
SEED_USER_SCOPES = f"""
INSERT INTO user_scopes (user_id, scope_type, scope_value) VALUES
  ('{ACTIVE_USER_ID}','pod','POD_A'),
  ('{ACTIVE_USER_ID}','publisher','PubX');
"""
SEED_STATEMENTS = (
    SEED_ROLES,
    SEED_PERMS,
    SEED_CAPS,
    SEED_USERS,
    SEED_USER_ROLES,
    SEED_USER_SCOPES,
)


class FakeRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis (get/set with TTL)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


class FakeVerifier:
    """Maps known tokens to decoded claims; raises on anything else."""

    def __init__(self, mapping: dict[str, dict[str, Any]]) -> None:
        self.mapping = mapping

    def verify(self, token: str) -> dict[str, Any]:
        from app.core.security import InvalidTokenError

        if token not in self.mapping:
            raise InvalidTokenError("malformed token")
        return self.mapping[token]


@dataclass
class AuthEnv:
    client: AsyncClient
    sessionmaker: async_sessionmaker[Any]
    redis: FakeRedis


async def _build_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        for stmt in SEED_STATEMENTS:
            await conn.execute(text(stmt))


@pytest_asyncio.fixture
async def auth_env() -> AsyncGenerator[AuthEnv, None]:
    from app.core.database import get_db, get_sessionmaker
    from app.core.redis import get_redis
    from app.core.security import get_token_verifier
    from app.main import app

    engine = create_async_engine(TEST_DATABASE_URL)
    await _build_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[Any, None]:
        async with session_factory() as session:
            yield session

    fake_redis = FakeRedis()
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_token_verifier] = lambda: FakeVerifier(TOKEN_MAP)
    # Route the audit service (dependency) and the audit middleware at the test DB.
    app.dependency_overrides[get_sessionmaker] = lambda: session_factory
    previous_sessionmaker = app.state.sessionmaker
    app.state.sessionmaker = session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield AuthEnv(client=client, sessionmaker=session_factory, redis=fake_redis)

    app.dependency_overrides.clear()
    app.state.sessionmaker = previous_sessionmaker
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[Any, None]:
    """A session against a freshly built + seeded test database."""
    engine = create_async_engine(TEST_DATABASE_URL)
    await _build_schema(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def db_sessionmaker() -> AsyncGenerator[async_sessionmaker[Any], None]:
    """A session factory against a freshly built + seeded test database."""
    engine = create_async_engine(TEST_DATABASE_URL)
    await _build_schema(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()

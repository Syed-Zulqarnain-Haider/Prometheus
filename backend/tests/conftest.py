"""Test configuration and fixtures.

Sets safe placeholder env vars BEFORE the app/config modules are imported, then
provides an integration test harness for the auth routes: a real Postgres test
database (schema + seed data), a fake Redis cache, and a fake token verifier
(no network / no real Firebase project).
"""

import os
import uuid as uuid_module
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
from sqlalchemy import insert, text  # noqa: E402
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
    """Minimal in-memory stand-in for redis.asyncio.Redis: get/set plus the
    sorted-set ops the per-user rate limiter uses (zadd/zcard/zrange/expire)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.zsets.setdefault(key, {}).update(mapping)

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        z = self.zsets.get(key)
        if not z:
            return
        for member in [m for m, s in z.items() if min_score <= s <= max_score]:
            del z[member]

    async def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    async def zrange(self, key: str, start: int, stop: int, withscores: bool = False) -> list[Any]:
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        sliced = items[start:] if stop == -1 else items[start : stop + 1]
        return [(m, s) for m, s in sliced] if withscores else [m for m, _ in sliced]

    async def expire(self, key: str, seconds: int) -> bool:
        return True


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


REDIS_TEST_URL = os.environ.setdefault("REDIS_TEST_URL", "redis://127.0.0.1:6390/0")

METRICS_ROLES = ["admin", "executive", "pod_owner", "marketing", "finance", "viewer"]
_METRICS_NS = uuid_module.UUID("00000000-0000-0000-0000-0000000000bb")
METRICS_TOKENS: dict[str, dict[str, Any]] = {
    f"valid-{role}": {"uid": f"{role}-uid"} for role in METRICS_ROLES
}
METRICS_TOKENS["valid-pod_owner_scoped"] = {"uid": "pod_owner_scoped-uid"}


def _metrics_uid(name: str) -> str:
    return str(uuid_module.uuid5(_METRICS_NS, name))


@dataclass
class MetricsEnv:
    client: AsyncClient
    sessionmaker: async_sessionmaker[Any]
    redis: Any


async def _seed_metrics_fact(session: Any) -> None:
    from datetime import date

    from app.core.fact_table import FACT_TABLE

    rows: list[dict[str, Any]] = [
        # appA / POD_A: two days → totals rev=1000, spend=250, paid=100, installs=100,
        # iap_gross=800, ad=100, tech_cost=30 → net_revenue=750, gross_profit=620.
        {
            "date": date(2026, 6, 1),
            "canonical_key": "appA",
            "pod": "POD_A",
            "publisher": "PubA",
            "store_total_installs": 40,
            "total_revenue_usd": 600,
            "total_ua_spend_usd": 100,
            "total_ad_revenue_usd": 50,
            "total_iap_gross_usd": 500,
            "tech_cost_usd": 20,
            "total_paid_installs": 40,
        },
        {
            "date": date(2026, 6, 2),
            "canonical_key": "appA",
            "pod": "POD_A",
            "publisher": "PubA",
            "store_total_installs": 60,
            "total_revenue_usd": 400,
            "total_ua_spend_usd": 150,
            "total_ad_revenue_usd": 50,
            "total_iap_gross_usd": 300,
            "tech_cost_usd": 10,
            "total_paid_installs": 60,
        },
        # appB / POD_B
        {
            "date": date(2026, 6, 1),
            "canonical_key": "appB",
            "pod": "POD_B",
            "publisher": "PubB",
            "store_total_installs": 7,
            "total_revenue_usd": 70,
            "total_ua_spend_usd": 10,
            "total_ad_revenue_usd": 5,
            "total_paid_installs": 5,
        },
        # appZ / POD_A: zero-denominator case (revenue, no spend/installs)
        {
            "date": date(2026, 6, 1),
            "canonical_key": "appZ",
            "pod": "POD_A",
            "publisher": "PubA",
            "store_total_installs": 0,
            "total_revenue_usd": 10,
            "total_ua_spend_usd": 0,
            "total_ad_revenue_usd": 0,
            "total_paid_installs": 0,
        },
    ]
    for r in rows:
        base = {
            "platform": "ios",
            "app_name": str(r["canonical_key"]).upper(),
            "pod_owner": "PO",
            "hou": "HOU_A",
        }
        await session.execute(insert(FACT_TABLE).values(**{**base, **r}))


@pytest_asyncio.fixture
async def metrics_env() -> AsyncGenerator[MetricsEnv, None]:
    from datetime import UTC, datetime

    import redis.asyncio as aioredis
    from app.core.database import get_db, get_sessionmaker
    from app.core.fact_table import fact_metadata
    from app.core.redis import get_redis
    from app.core.security import get_token_verifier
    from app.main import app
    from app.models import DimApp, SyncRun

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(fact_metadata.drop_all)
        await conn.run_sync(fact_metadata.create_all)
    async with engine.begin() as conn:
        for stmt in (SEED_ROLES, SEED_PERMS, SEED_CAPS):
            await conn.execute(text(stmt))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        users = [(role, _metrics_uid(role), f"{role}-uid", "all", None) for role in METRICS_ROLES]
        users.append(
            ("pod_owner", _metrics_uid("pod_owner_scoped"), "pod_owner_scoped-uid", "pod", "POD_A")
        )
        for role, uid, fb, scope_type, scope_value in users:
            await session.execute(
                text(
                    "INSERT INTO users (id, firebase_uid, email, is_active) "
                    "VALUES (:id, :fb, :email, true)"
                ),
                {"id": uid, "fb": fb, "email": f"{fb}@terafort.org"},
            )
            await session.execute(
                text(
                    "INSERT INTO user_roles (user_id, role_id) SELECT :id, id FROM roles WHERE name=:role"
                ),
                {"id": uid, "role": role},
            )
            await session.execute(
                text(
                    "INSERT INTO user_scopes (user_id, scope_type, scope_value) "
                    "VALUES (:id, :st, :sv)"
                ),
                {"id": uid, "st": scope_type, "sv": scope_value},
            )
        await _seed_metrics_fact(session)
        for ck, pod, pub in [
            ("appA", "POD_A", "PubA"),
            ("appB", "POD_B", "PubB"),
            ("appZ", "POD_A", "PubA"),
        ]:
            await session.execute(
                insert(DimApp).values(
                    canonical_key=ck,
                    app_name=ck.upper(),
                    publisher=pub,
                    pod=pod,
                    pod_owner="PO",
                    hou="HOU_A",
                    is_mapped=True,
                )
            )
        await session.execute(
            insert(SyncRun).values(
                status="success",
                bq_built_at=datetime(2026, 6, 2, 6, 0, tzinfo=UTC),
                finished_at=datetime(2026, 6, 2, 6, 5, tzinfo=UTC),
                rows_loaded=100,
            )
        )
        await session.commit()

    redis_client = aioredis.from_url(REDIS_TEST_URL, decode_responses=True)
    await redis_client.flushdb()

    async def _override_get_db() -> AsyncGenerator[Any, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_sessionmaker] = lambda: session_factory
    app.dependency_overrides[get_redis] = lambda: redis_client
    app.dependency_overrides[get_token_verifier] = lambda: FakeVerifier(METRICS_TOKENS)
    previous_sessionmaker = app.state.sessionmaker
    app.state.sessionmaker = session_factory

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield MetricsEnv(client=client, sessionmaker=session_factory, redis=redis_client)

    app.dependency_overrides.clear()
    app.state.sessionmaker = previous_sessionmaker
    await redis_client.aclose()
    await engine.dispose()


@pytest_asyncio.fixture
async def fact_session() -> AsyncGenerator[Any, None]:
    """A session with a fresh, empty ``fact_daily_performance`` table.

    The fact table is sync-owned (its own MetaData), so we create just it here for
    query-builder tests that seed fact rows directly.
    """
    from app.core.fact_table import fact_metadata

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(fact_metadata.drop_all)
        await conn.run_sync(fact_metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()

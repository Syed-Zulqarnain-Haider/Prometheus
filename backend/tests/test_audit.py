"""Audit service + middleware tests.

Asserts rows are written for the explicit helpers and the api_query middleware,
and that the service/middleware NEVER raise into the request path (log-and-continue).
"""

import uuid
from types import SimpleNamespace
from typing import Any

from app.api.middleware import audit_query_middleware, is_data_route
from app.models import AuditLog
from app.services.audit import AuditService
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conftest import ACTIVE_USER_ID

ACTIVE_UID = uuid.UUID(ACTIVE_USER_ID)


async def _actions(sessionmaker: async_sessionmaker[Any]) -> list[tuple[str, str | None]]:
    async with sessionmaker() as session:
        rows = (await session.execute(select(AuditLog.action, AuditLog.resource))).all()
    return [(a, r) for a, r in rows]


# ── Explicit helpers write rows ──────────────────────────────────────────────
async def test_helpers_write_expected_rows(db_sessionmaker) -> None:
    service = AuditService(db_sessionmaker)
    await service.log_login(user_id=ACTIVE_UID, ip="1.2.3.4", user_agent="UA")
    await service.log_export(user_id=ACTIVE_UID, resource="/export/csv", detail={"rows": 10})
    await service.log_admin_action(user_id=ACTIVE_UID, action="create_user", resource="users/x")

    rows = await _actions(db_sessionmaker)
    assert ("login", None) in rows
    assert ("export", "/export/csv") in rows
    assert ("create_user", "users/x") in rows
    assert len(rows) == 3


async def test_write_persists_all_fields(db_sessionmaker) -> None:
    service = AuditService(db_sessionmaker)
    await service.write(
        user_id=ACTIVE_UID,
        action="api_query",
        resource="/api/v1/metrics/summary",
        detail={"method": "GET", "query": {"platform": "ios"}},
        ip="10.0.0.1",
        user_agent="pytest",
    )
    async with db_sessionmaker() as session:
        entry = (await session.execute(select(AuditLog))).scalars().one()
    assert entry.action == "api_query"
    assert entry.detail == {"method": "GET", "query": {"platform": "ios"}}
    assert str(entry.ip_address) == "10.0.0.1"
    assert entry.user_agent == "pytest"


# ── Never raises into the request path ───────────────────────────────────────
class _BoomSessionmaker:
    def __call__(self) -> Any:
        raise RuntimeError("db is down")


async def test_write_swallows_failures() -> None:
    service = AuditService(_BoomSessionmaker())  # type: ignore[arg-type]
    # Must NOT raise even though the session factory explodes.
    await service.write(user_id=ACTIVE_UID, action="login")


# ── api_query middleware ─────────────────────────────────────────────────────
def test_is_data_route() -> None:
    assert is_data_route("/api/v1/metrics/summary")
    assert is_data_route("/api/v1/apps/abc")
    assert not is_data_route("/api/v1/auth/me")
    assert not is_data_route("/health")


def _build_probe_app(sessionmaker: Any, *, authenticated: bool) -> FastAPI:
    app = FastAPI()
    app.state.sessionmaker = sessionmaker
    app.middleware("http")(audit_query_middleware)

    @app.get("/api/v1/metrics/summary")
    async def metrics(request: Request) -> dict[str, bool]:
        if authenticated:
            request.state.user_context = SimpleNamespace(user_id=ACTIVE_UID)
        return {"ok": True}

    @app.get("/api/v1/auth/me")
    async def me(request: Request) -> dict[str, bool]:
        request.state.user_context = SimpleNamespace(user_id=ACTIVE_UID)
        return {"ok": True}

    return app


async def _get(app: FastAPI, path: str) -> int:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    return response.status_code


async def test_middleware_logs_api_query_for_data_route(db_sessionmaker) -> None:
    app = _build_probe_app(db_sessionmaker, authenticated=True)
    assert await _get(app, "/api/v1/metrics/summary?platform=ios") == 200

    async with db_sessionmaker() as session:
        entry = (await session.execute(select(AuditLog))).scalars().one()
    assert entry.action == "api_query"
    assert entry.resource == "/api/v1/metrics/summary"
    assert entry.detail["method"] == "GET"
    assert entry.detail["query"] == {"platform": "ios"}


async def test_middleware_skips_non_data_route(db_sessionmaker) -> None:
    app = _build_probe_app(db_sessionmaker, authenticated=True)
    assert await _get(app, "/api/v1/auth/me") == 200
    assert await _actions(db_sessionmaker) == []


async def test_middleware_skips_unauthenticated(db_sessionmaker) -> None:
    app = _build_probe_app(db_sessionmaker, authenticated=False)
    assert await _get(app, "/api/v1/metrics/summary") == 200
    assert await _actions(db_sessionmaker) == []


async def test_middleware_never_breaks_request_on_audit_failure() -> None:
    app = _build_probe_app(_BoomSessionmaker(), authenticated=True)
    # The audit write blows up, but the request must still succeed.
    assert await _get(app, "/api/v1/metrics/summary") == 200

"""Auth dependency + route tests (mocked token verifier, real Postgres, fake Redis)."""

from app.models import AuditLog
from sqlalchemy import func, select

from tests.conftest import ACTIVE_USER_ID, AuthEnv

ME_URL = "/api/v1/auth/me"
SESSION_URL = "/api/v1/auth/session"


async def test_me_active_user_returns_full_rbac(auth_env: AuthEnv) -> None:
    response = await auth_env.client.get(ME_URL, headers={"Authorization": "Bearer valid-active"})
    assert response.status_code == 200
    data = response.json()
    assert data["roles"] == ["marketing"]
    # marketing includes iap_revenue (owner decision) but not attribution.
    assert set(data["metric_groups"]) == {
        "store_installs",
        "ua_spend",
        "ad_revenue",
        "iap_revenue",
        "profitability",
    }
    assert set(data["capabilities"]) == {"export", "share_report"}
    scopes = {(s["scope_type"], s["scope_value"]) for s in data["scopes"]}
    assert scopes == {("pod", "POD_A"), ("publisher", "PubX")}


async def test_inactive_user_rejected(auth_env: AuthEnv) -> None:
    response = await auth_env.client.get(ME_URL, headers={"Authorization": "Bearer valid-inactive"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_unknown_uid_rejected(auth_env: AuthEnv) -> None:
    response = await auth_env.client.get(ME_URL, headers={"Authorization": "Bearer valid-unknown"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_malformed_token_rejected(auth_env: AuthEnv) -> None:
    response = await auth_env.client.get(
        ME_URL, headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_missing_token_rejected(auth_env: AuthEnv) -> None:
    response = await auth_env.client.get(ME_URL)
    assert response.status_code == 401


async def test_session_writes_login_audit(auth_env: AuthEnv) -> None:
    response = await auth_env.client.post(
        SESSION_URL, headers={"Authorization": "Bearer valid-active"}
    )
    assert response.status_code == 200

    async with auth_env.sessionmaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "login", AuditLog.user_id == ACTIVE_USER_ID)
        )
    assert count == 1


async def test_resolved_context_is_cached(auth_env: AuthEnv) -> None:
    await auth_env.client.get(ME_URL, headers={"Authorization": "Bearer valid-active"})
    assert any(key.startswith("userctx:") for key in auth_env.redis.store)

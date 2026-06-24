"""Tests for the access-request queue (Admin feature PR 2).

An authenticated-but-unprovisioned sign-in records a PENDING request (idempotent, grants
ZERO access). An admin approves (role + scope + optional expiry -> provisions) or rejects
(stays no-access, may re-request). Admin-only + audited.
"""

import uuid

from app.models import AccessRequest, User
from sqlalchemy import select

from tests.conftest import MetricsEnv

_NEWCOMER_UID = "newcomer-uid"
_DUMMY = "00000000-0000-0000-0000-0000000000aa"


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _request_id(env: MetricsEnv) -> str:
    await env.client.post("/api/v1/auth/access-request", headers=_auth("newcomer"))
    pending = (await env.client.get("/api/v1/admin/access-requests", headers=_auth("admin"))).json()
    return next(r["id"] for r in pending if r["firebase_uid"] == _NEWCOMER_UID)


# ── recording ─────────────────────────────────────────────────────────────────
async def test_access_request_requires_authentication(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post("/api/v1/auth/access-request")
    assert resp.status_code == 401


async def test_unprovisioned_signin_records_pending_request(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    resp = await c.post("/api/v1/auth/access-request", headers=_auth("newcomer"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    pending = (await c.get("/api/v1/admin/access-requests", headers=_auth("admin"))).json()
    rows = [r for r in pending if r["firebase_uid"] == _NEWCOMER_UID]
    assert len(rows) == 1
    assert rows[0]["email"] == "newcomer@terafort.org"
    assert rows[0]["status"] == "pending"


async def test_access_request_is_idempotent(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    await c.post("/api/v1/auth/access-request", headers=_auth("newcomer"))
    await c.post("/api/v1/auth/access-request", headers=_auth("newcomer"))

    async with metrics_env.sessionmaker() as s:
        count = await s.scalar(
            select(AccessRequest).where(AccessRequest.firebase_uid == _NEWCOMER_UID)
        )
    assert count is not None
    pending = (await c.get("/api/v1/admin/access-requests", headers=_auth("admin"))).json()
    assert len([r for r in pending if r["firebase_uid"] == _NEWCOMER_UID]) == 1  # no dupes


async def test_request_grants_zero_access(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    await c.post("/api/v1/auth/access-request", headers=_auth("newcomer"))
    # Still unprovisioned — no account, no role.
    assert (await c.get("/api/v1/auth/me", headers=_auth("newcomer"))).status_code == 401
    async with metrics_env.sessionmaker() as s:
        user = await s.scalar(select(User).where(User.firebase_uid == _NEWCOMER_UID))
    assert user is None


# ── admin-only ────────────────────────────────────────────────────────────────
async def test_access_request_admin_endpoints_require_admin(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    for role in ("viewer", "executive", "finance"):
        assert (
            await c.get("/api/v1/admin/access-requests", headers=_auth(role))
        ).status_code == 403
        assert (
            await c.post(
                f"/api/v1/admin/access-requests/{_DUMMY}/approve",
                json={"roles": ["viewer"], "scopes": []},
                headers=_auth(role),
            )
        ).status_code == 403
        assert (
            await c.post(f"/api/v1/admin/access-requests/{_DUMMY}/reject", headers=_auth(role))
        ).status_code == 403


# ── approve / reject ──────────────────────────────────────────────────────────
async def test_approve_provisions_user_with_expiry_and_audits(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    request_id = await _request_id(metrics_env)

    approved = await c.post(
        f"/api/v1/admin/access-requests/{request_id}/approve",
        json={
            "roles": ["viewer"],
            "scopes": [{"scope_type": "all", "scope_value": None}],
            "access_duration_days": 30,
        },
        headers=_auth("admin"),
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["roles"] == ["viewer"]
    assert body["access_expires_at"] is not None
    assert body["is_expired"] is False

    # The newcomer now has access (until expiry); the request is no longer pending.
    assert (await c.get("/api/v1/auth/me", headers=_auth("newcomer"))).status_code == 200
    pending = (await c.get("/api/v1/admin/access-requests", headers=_auth("admin"))).json()
    assert not [r for r in pending if r["firebase_uid"] == _NEWCOMER_UID]

    async with metrics_env.sessionmaker() as s:
        from app.models import AuditLog

        actions = (
            (
                await s.execute(
                    select(AuditLog.action).where(AuditLog.action == "admin_approve_access")
                )
            )
            .scalars()
            .all()
        )
    assert "admin_approve_access" in actions


async def test_reject_keeps_zero_access_and_allows_rerequest(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    request_id = await _request_id(metrics_env)

    rejected = await c.post(
        f"/api/v1/admin/access-requests/{request_id}/reject", headers=_auth("admin")
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # No access, and dropped from the pending list.
    assert (await c.get("/api/v1/auth/me", headers=_auth("newcomer"))).status_code == 401
    pending = (await c.get("/api/v1/admin/access-requests", headers=_auth("admin"))).json()
    assert not [r for r in pending if r["firebase_uid"] == _NEWCOMER_UID]

    # Re-request: signing in again re-opens the request (back to pending, no dupe).
    await c.post("/api/v1/auth/access-request", headers=_auth("newcomer"))
    pending = (await c.get("/api/v1/admin/access-requests", headers=_auth("admin"))).json()
    assert len([r for r in pending if r["firebase_uid"] == _NEWCOMER_UID]) == 1


async def test_approve_and_reject_unknown_request_404(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    approve = await c.post(
        f"/api/v1/admin/access-requests/{uuid.uuid4()}/approve",
        json={"roles": ["viewer"], "scopes": []},
        headers=_auth("admin"),
    )
    assert approve.status_code == 404
    reject = await c.post(
        f"/api/v1/admin/access-requests/{uuid.uuid4()}/reject", headers=_auth("admin")
    )
    assert reject.status_code == 404

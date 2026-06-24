"""Tests for Admin user CRUD + time-limited access (Admin feature PR 1).

Covers: DELETE with the self / last-active-admin guards; hard-delete preserving the
append-only audit trail (FK SET NULL); the last-admin guard on demote / deactivate /
past-expiry (but allowing a FUTURE expiry); and server-side enforcement that an expired
user is denied everywhere (even if the UI is bypassed).
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import AuditLog, User
from sqlalchemy import insert, select

from tests.conftest import MetricsEnv, _metrics_uid


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def _uid(name: str) -> str:
    return _metrics_uid(name)


# ── DELETE: admin-only + guards ───────────────────────────────────────────────
async def test_delete_user_requires_admin(metrics_env: MetricsEnv) -> None:
    for role in ("viewer", "executive", "finance"):
        resp = await metrics_env.client.delete(
            f"/api/v1/admin/users/{_uid('viewer')}", headers=_auth(role)
        )
        assert resp.status_code == 403, f"{role} reached DELETE"


async def test_admin_cannot_delete_self(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.delete(
        f"/api/v1/admin/users/{_uid('admin')}", headers=_auth("admin")
    )
    assert resp.status_code == 400
    assert "own account" in resp.json()["error"]["message"].lower()
    # still present
    async with metrics_env.sessionmaker() as s:
        assert await s.get(User, uuid.UUID(_uid("admin"))) is not None


async def test_delete_user_success_and_audited(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    created = await c.post(
        "/api/v1/admin/users",
        json={"firebase_uid": "temp-uid", "email": "temp@terafort.org", "roles": ["viewer"]},
        headers=_auth("admin"),
    )
    assert created.status_code == 201
    new_id = created.json()["id"]

    deleted = await c.delete(f"/api/v1/admin/users/{new_id}", headers=_auth("admin"))
    assert deleted.status_code == 204

    listing = (await c.get("/api/v1/admin/users", headers=_auth("admin"))).json()
    assert new_id not in {u["id"] for u in listing}

    async with metrics_env.sessionmaker() as s:
        actions = (
            (await s.execute(select(AuditLog.action).where(AuditLog.action == "admin_delete_user")))
            .scalars()
            .all()
        )
    assert "admin_delete_user" in actions


async def test_hard_delete_preserves_audit_trail(metrics_env: MetricsEnv) -> None:
    """Deleting a user keeps their audit rows (content intact, user_id nulled)."""
    finance_id = uuid.UUID(_uid("finance"))
    async with metrics_env.sessionmaker() as s:
        await s.execute(insert(AuditLog).values(user_id=finance_id, action="zz_probe_event"))
        await s.commit()

    resp = await metrics_env.client.delete(
        f"/api/v1/admin/users/{finance_id}", headers=_auth("admin")
    )
    assert resp.status_code == 204  # succeeds despite the audit reference

    async with metrics_env.sessionmaker() as s:
        row = (
            await s.execute(select(AuditLog).where(AuditLog.action == "zz_probe_event"))
        ).scalar_one()
        assert row.user_id is None  # SET NULL preserved the row, unlinked the user
        assert await s.get(User, finance_id) is None


# ── Last-active-admin lockout guard (update) ──────────────────────────────────
async def test_last_admin_cannot_be_deactivated(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.patch(
        f"/api/v1/admin/users/{_uid('admin')}",
        json={"is_active": False},
        headers=_auth("admin"),
    )
    assert resp.status_code == 400
    assert "last active admin" in resp.json()["error"]["message"].lower()


async def test_last_admin_cannot_be_demoted(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.patch(
        f"/api/v1/admin/users/{_uid('admin')}",
        json={"roles": ["viewer"]},
        headers=_auth("admin"),
    )
    assert resp.status_code == 400


async def test_last_admin_cannot_be_expired_in_the_past(metrics_env: MetricsEnv) -> None:
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    resp = await metrics_env.client.patch(
        f"/api/v1/admin/users/{_uid('admin')}",
        json={"access_expires_at": past},
        headers=_auth("admin"),
    )
    assert resp.status_code == 400


async def test_last_admin_future_expiry_is_allowed(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.patch(
        f"/api/v1/admin/users/{_uid('admin')}",
        json={"access_duration_days": 30},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    assert resp.json()["access_expires_at"] is not None
    assert resp.json()["is_expired"] is False


# ── Time-limited access: server-side enforcement ──────────────────────────────
async def test_expired_user_is_denied_everywhere(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    assert (await c.get("/api/v1/auth/me", headers=_auth("finance"))).status_code == 200

    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    upd = await c.patch(
        f"/api/v1/admin/users/{_uid('finance')}",
        json={"access_expires_at": past},
        headers=_auth("admin"),
    )
    assert upd.status_code == 200
    assert upd.json()["is_expired"] is True

    # Server denies — even on the cached path (cache busted on the change).
    assert (await c.get("/api/v1/auth/me", headers=_auth("finance"))).status_code == 403
    summary = await c.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
        headers=_auth("finance"),
    )
    assert summary.status_code == 403


async def test_future_expiry_user_keeps_access(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    upd = await c.patch(
        f"/api/v1/admin/users/{_uid('finance')}",
        json={"access_duration_days": 30},
        headers=_auth("admin"),
    )
    assert upd.status_code == 200
    assert (await c.get("/api/v1/auth/me", headers=_auth("finance"))).status_code == 200


# ── Expiry inputs ─────────────────────────────────────────────────────────────
async def test_create_user_with_duration(metrics_env: MetricsEnv) -> None:
    created = await metrics_env.client.post(
        "/api/v1/admin/users",
        json={
            "firebase_uid": "dur-uid",
            "email": "dur@terafort.org",
            "roles": ["viewer"],
            "access_duration_days": 30,
        },
        headers=_auth("admin"),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["access_expires_at"] is not None
    assert body["is_expired"] is False


async def test_rejects_both_expiry_fields(metrics_env: MetricsEnv) -> None:
    future = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    resp = await metrics_env.client.patch(
        f"/api/v1/admin/users/{_uid('viewer')}",
        json={"access_expires_at": future, "access_duration_days": 30},
        headers=_auth("admin"),
    )
    assert resp.status_code == 400
    assert "not both" in resp.json()["error"]["message"].lower()

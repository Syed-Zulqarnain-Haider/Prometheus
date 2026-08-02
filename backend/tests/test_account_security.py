"""Account security: 2FA status, recent device activity, and sign-out-everywhere."""

from __future__ import annotations

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def test_security_status_shape(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/me/security", headers=_auth("executive"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["two_factor"] is False  # the fake token carries no second-factor claim
    assert body["sessions_revoked_at"] is None
    assert isinstance(body["devices"], list)


async def test_security_requires_auth(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/me/security")
    assert resp.status_code == 401


async def test_revoke_sessions_signs_out_old_tokens(metrics_env: MetricsEnv) -> None:
    # Revoke succeeds (the request's own token pre-dates the revoke instant).
    revoke = await metrics_env.client.post(
        "/api/v1/me/security/revoke-sessions", headers=_auth("executive")
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"]

    # The same token (issued in 2023) is now rejected everywhere — live, on the next request.
    after = await metrics_env.client.get("/api/v1/me/security", headers=_auth("executive"))
    assert after.status_code == 401

    # A DIFFERENT user is unaffected (revocation is per-user).
    other = await metrics_env.client.get("/api/v1/me/security", headers=_auth("admin"))
    assert other.status_code == 200


async def test_revoke_is_scoped_to_caller(metrics_env: MetricsEnv) -> None:
    # Marketing revokes only their own sessions; the viewer keeps working.
    await metrics_env.client.post(
        "/api/v1/me/security/revoke-sessions", headers=_auth("marketing")
    )
    viewer = await metrics_env.client.get("/api/v1/me/security", headers=_auth("viewer"))
    assert viewer.status_code == 200

"""Opt-in 2FA enforcement for admin actions, plus admin force-logout — with break-glass."""

from __future__ import annotations

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _set_require_2fa(env: MetricsEnv, value: bool, *, token: str = "admin") -> int:
    resp = await env.client.put(
        "/api/v1/admin/settings/require_admin_2fa",
        json={"value": value},
        headers=_auth(token),
    )
    return resp.status_code


async def test_off_by_default_admin_works_without_2fa(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/admin/users", headers=_auth("admin"))
    assert resp.status_code == 200


async def test_enforced_blocks_non_2fa_admin(metrics_env: MetricsEnv) -> None:
    # Enabled via the Settings route (break-glass), which a non-2FA admin may always reach.
    assert await _set_require_2fa(metrics_env, True) == 200
    resp = await metrics_env.client.get("/api/v1/admin/users", headers=_auth("admin"))
    assert resp.status_code == 403


async def test_enforced_allows_2fa_admin(metrics_env: MetricsEnv) -> None:
    assert await _set_require_2fa(metrics_env, True) == 200
    resp = await metrics_env.client.get("/api/v1/admin/users", headers=_auth("admin_2fa"))
    assert resp.status_code == 200


async def test_settings_route_is_breakglass(metrics_env: MetricsEnv) -> None:
    assert await _set_require_2fa(metrics_env, True) == 200
    # Non-2FA admin is blocked on a normal admin action…
    blocked = await metrics_env.client.get("/api/v1/admin/users", headers=_auth("admin"))
    assert blocked.status_code == 403
    # …but can ALWAYS turn the requirement back off (so you can't lock yourself out).
    assert await _set_require_2fa(metrics_env, False) == 200
    ok = await metrics_env.client.get("/api/v1/admin/users", headers=_auth("admin"))
    assert ok.status_code == 200


async def test_admin_force_logout_user(metrics_env: MetricsEnv) -> None:
    users = (
        await metrics_env.client.get("/api/v1/admin/users", headers=_auth("admin"))
    ).json()
    exec_id = next(u["id"] for u in users if u["email"] == "executive-uid@terafort.org")

    revoke = await metrics_env.client.post(
        f"/api/v1/admin/users/{exec_id}/revoke-sessions", headers=_auth("admin")
    )
    assert revoke.status_code == 200

    # The executive's existing (older) token is now rejected on its next request.
    after = await metrics_env.client.get("/api/v1/me/security", headers=_auth("executive"))
    assert after.status_code == 401

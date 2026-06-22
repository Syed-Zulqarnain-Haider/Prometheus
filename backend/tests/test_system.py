"""Integration tests for the admin System tab: connection health, operational
settings (and that the backend respects them), and the on-demand sync trigger.

Security focus: every System endpoint is admin-only, changes are audited, and NO
secret/credential ever appears in a response.
"""

import json
from typing import Any

from app.models import AuditLog
from sqlalchemy import select

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


# ── Admin-only access ────────────────────────────────────────────────────────
async def test_system_endpoints_require_admin(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    for method, path in [
        ("get", "/api/v1/admin/system/health"),
        ("get", "/api/v1/admin/settings"),
        ("post", "/api/v1/admin/system/sync"),
    ]:
        call = getattr(c, method)
        resp = await call(path, headers=_auth("viewer"))
        assert resp.status_code == 403, f"viewer reached {method.upper()} {path}"
    bad = await c.put(
        "/api/v1/admin/settings/show_demo_widgets",
        json={"value": False},
        headers=_auth("finance"),
    )
    assert bad.status_code == 403


# ── Connection health: status only, never a credential ───────────────────────
async def test_system_health_reports_status_no_secrets(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/admin/system/health", headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["postgres"]["status"] == "up"
    assert body["redis"]["status"] == "up"
    assert body["bigquery"]["status"] == "not_configured"  # no BQ wired locally
    assert isinstance(body["postgres"]["latency_ms"], (int, float))

    # No connection string / credential anywhere in the payload.
    blob = json.dumps(body)
    for needle in ("postgresql://", "redis://", "password", "@", "://"):
        assert needle not in blob, f"health payload leaked '{needle}'"


# ── Operational settings: list, defaults, validation, audit ──────────────────
async def test_settings_list_exposes_defaults(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/admin/settings", headers=_auth("admin"))
    assert resp.status_code == 200
    by_key = {s["key"]: s for s in resp.json()}
    assert by_key["data_freshness_threshold_hours"]["value"] == 48
    assert by_key["show_demo_widgets"]["value"] is True


async def test_setting_update_persists_and_is_audited(metrics_env: MetricsEnv) -> None:
    put = await metrics_env.client.put(
        "/api/v1/admin/settings/show_demo_widgets",
        json={"value": False},
        headers=_auth("admin"),
    )
    assert put.status_code == 200
    assert put.json()["value"] is False

    got = await metrics_env.client.get("/api/v1/admin/settings", headers=_auth("admin"))
    by_key = {s["key"]: s for s in got.json()}
    assert by_key["show_demo_widgets"]["value"] is False

    async with metrics_env.sessionmaker() as session:
        actions = (
            (
                await session.execute(
                    select(AuditLog.action).where(AuditLog.action == "admin_update_setting")
                )
            )
            .scalars()
            .all()
        )
    assert "admin_update_setting" in actions


async def test_setting_rejects_out_of_bounds_and_unknown(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    too_big = await c.put(
        "/api/v1/admin/settings/data_freshness_threshold_hours",
        json={"value": 100000},
        headers=_auth("admin"),
    )
    assert too_big.status_code == 400
    unknown = await c.put(
        "/api/v1/admin/settings/database_url",  # a "secret-y" key is simply unknown
        json={"value": 1},
        headers=_auth("admin"),
    )
    assert unknown.status_code == 400


# ── Backend genuinely respects the freshness threshold ───────────────────────
async def test_freshness_threshold_drives_staleness(metrics_env: MetricsEnv) -> None:
    """The seed's last successful build is fixed in the past, so a 1h threshold marks
    it stale while a 720h threshold does not — proving data_health reads the setting."""
    c = metrics_env.client

    await c.put(
        "/api/v1/admin/settings/data_freshness_threshold_hours",
        json={"value": 1},
        headers=_auth("admin"),
    )
    health = (await c.get("/api/v1/admin/data-health", headers=_auth("admin"))).json()
    assert health["is_stale"] is True

    await c.put(
        "/api/v1/admin/settings/data_freshness_threshold_hours",
        json={"value": 720},
        headers=_auth("admin"),
    )
    health = (await c.get("/api/v1/admin/data-health", headers=_auth("admin"))).json()
    assert health["is_stale"] is False


# ── Client-facing settings (any authenticated user) ──────────────────────────
async def test_client_settings_reflect_admin_changes(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    before = (await c.get("/api/v1/meta/settings", headers=_auth("viewer"))).json()
    assert before["show_demo_widgets"] is True

    await c.put(
        "/api/v1/admin/settings/show_demo_widgets",
        json={"value": False},
        headers=_auth("admin"),
    )
    after = (await c.get("/api/v1/meta/settings", headers=_auth("viewer"))).json()
    assert after["show_demo_widgets"] is False


# ── Run sync now: honest 'not configured', audited, rate-limited ─────────────
async def test_run_sync_not_configured_is_honest(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post("/api/v1/admin/system/sync", headers=_auth("admin"))
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    assert body["triggered"] is False
    assert body["configured"] is False
    assert "not configured" in body["message"].lower()

    async with metrics_env.sessionmaker() as session:
        stmt = select(AuditLog.action).where(AuditLog.action == "admin_run_sync")
        actions = (await session.execute(stmt)).scalars().all()
    assert "admin_run_sync" in actions


async def test_run_sync_is_rate_limited(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    for _ in range(3):  # SYNC_RATE_LIMIT = 3 / min
        ok = await c.post("/api/v1/admin/system/sync", headers=_auth("admin"))
        assert ok.status_code == 200
    blocked = await c.post("/api/v1/admin/system/sync", headers=_auth("admin"))
    assert blocked.status_code == 429

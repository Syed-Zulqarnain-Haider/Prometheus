"""Integration tests for the admin panel (Step 7).

Covers the admin_panel capability gate, user CRUD with immediate cache busting on
RBAC changes, role configuration, revenue targets (incl. the public /meta/targets
read), the audit viewer, and the data-health view.
"""

import pytest

from tests.conftest import MetricsEnv, _metrics_uid


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


# ── Capability gate ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", ["viewer", "finance", "pod_owner"])
async def test_admin_routes_require_admin_capability(metrics_env: MetricsEnv, role: str) -> None:
    for path in ["/api/v1/admin/users", "/api/v1/admin/roles", "/api/v1/admin/data-health"]:
        resp = await metrics_env.client.get(path, headers=_auth(role))
        assert resp.status_code == 403, f"{role} reached {path}"


async def test_admin_can_list_users(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/admin/users", headers=_auth("admin"))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "finance-uid@terafort.org" in emails


# ── User management ───────────────────────────────────────────────────────────
async def test_create_user_and_conflict(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    body = {
        "firebase_uid": "new-analyst-uid",
        "email": "analyst@terafort.org",
        "display_name": "Ann Analyst",
        "roles": ["viewer"],
        "scopes": [{"scope_type": "pod", "scope_value": "POD_A"}],
    }
    created = await client.post("/api/v1/admin/users", json=body, headers=_auth("admin"))
    assert created.status_code == 201
    assert created.json()["roles"] == ["viewer"]
    assert created.json()["scopes"] == [{"scope_type": "pod", "scope_value": "POD_A"}]

    dup = await client.post("/api/v1/admin/users", json=body, headers=_auth("admin"))
    assert dup.status_code == 409


async def test_deactivation_busts_cache_immediately(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    # Finance logs in first -> context is cached in Redis.
    assert (await client.get("/api/v1/auth/me", headers=_auth("finance"))).status_code == 200

    deactivate = await client.patch(
        f"/api/v1/admin/users/{_metrics_uid('finance')}",
        json={"is_active": False},
        headers=_auth("admin"),
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    # Without cache busting this would still be 200 for up to 5 minutes.
    blocked = await client.get("/api/v1/auth/me", headers=_auth("finance"))
    assert blocked.status_code == 403


async def test_role_config_update_busts_cache(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    # Viewer logs in (store_installs only, no export).
    before = await client.get("/api/v1/auth/me", headers=_auth("viewer"))
    assert "profitability" not in before.json()["metric_groups"]

    roles = (await client.get("/api/v1/admin/roles", headers=_auth("admin"))).json()
    viewer_id = next(r["id"] for r in roles if r["name"] == "viewer")

    updated = await client.put(
        f"/api/v1/admin/roles/{viewer_id}",
        json={"metric_groups": ["store_installs", "profitability"], "capabilities": ["export"]},
        headers=_auth("admin"),
    )
    assert updated.status_code == 200

    after = await client.get("/api/v1/auth/me", headers=_auth("viewer"))
    assert "profitability" in after.json()["metric_groups"]
    assert "export" in after.json()["capabilities"]


async def test_role_update_rejects_unknown_group(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    roles = (await client.get("/api/v1/admin/roles", headers=_auth("admin"))).json()
    viewer_id = next(r["id"] for r in roles if r["name"] == "viewer")
    resp = await client.put(
        f"/api/v1/admin/roles/{viewer_id}",
        json={"metric_groups": ["not_a_group"], "capabilities": []},
        headers=_auth("admin"),
    )
    assert resp.status_code == 422


# ── Revenue targets ───────────────────────────────────────────────────────────
async def test_targets_upsert_and_public_read(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    await client.put(
        "/api/v1/admin/targets",
        json={"period_type": "year", "period_year": 2026, "target_usd": 1_200_000},
        headers=_auth("admin"),
    )
    await client.put(
        "/api/v1/admin/targets",
        json={
            "period_type": "month",
            "period_year": 2026,
            "period_month": 6,
            "target_usd": 100_000,
        },
        headers=_auth("admin"),
    )
    # Upsert (same period) updates rather than duplicating.
    await client.put(
        "/api/v1/admin/targets",
        json={
            "period_type": "month",
            "period_year": 2026,
            "period_month": 6,
            "target_usd": 120_000,
        },
        headers=_auth("admin"),
    )

    admin_view = await client.get("/api/v1/admin/targets?year=2026", headers=_auth("admin"))
    assert admin_view.json()["annual"]["target_usd"] == 1_200_000
    assert len(admin_view.json()["monthly"]) == 1
    assert admin_view.json()["monthly"][0]["target_usd"] == 120_000

    # Any authenticated user can read targets for the Overview donut.
    public = await client.get("/api/v1/meta/targets?year=2026", headers=_auth("viewer"))
    assert public.status_code == 200
    assert public.json()["annual"]["target_usd"] == 1_200_000


# ── Audit viewer ──────────────────────────────────────────────────────────────
async def test_audit_viewer_records_admin_actions(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    await client.put(
        "/api/v1/admin/targets",
        json={"period_type": "year", "period_year": 2026, "target_usd": 999},
        headers=_auth("admin"),
    )
    page = await client.get("/api/v1/admin/audit?action=admin_set_target", headers=_auth("admin"))
    assert page.status_code == 200
    actions = {entry["action"] for entry in page.json()["entries"]}
    assert actions == {"admin_set_target"}
    assert page.json()["entries"][0]["user_email"] == "admin-uid@terafort.org"


# ── Data health ───────────────────────────────────────────────────────────────
async def test_data_health_reports_sync_state(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/admin/data-health", headers=_auth("admin"))
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["last_status"] == "success"
    assert len(payload["recent_runs"]) >= 1
    assert payload["unmapped_count"] == 0
    assert isinstance(payload["warnings"], list)

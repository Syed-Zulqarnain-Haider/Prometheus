"""Integration tests for the admin panel (Step 7).

Covers the admin_panel capability gate, user CRUD with immediate cache busting on
RBAC changes, role configuration, revenue targets (incl. the public /meta/targets
read), the audit viewer, and the data-health view.
"""

from typing import Any

import pytest

from tests.conftest import MetricsEnv, _metrics_uid


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


# ── Capability gate ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", ["viewer", "finance", "pod_owner", "executive"])
async def test_admin_routes_require_admin_capability(metrics_env: MetricsEnv, role: str) -> None:
    for path in ["/api/v1/admin/users", "/api/v1/admin/roles", "/api/v1/admin/data-health"]:
        resp = await metrics_env.client.get(path, headers=_auth(role))
        assert resp.status_code == 403, f"{role} reached {path}"


# ── Executive = broad READ-ONLY viewer ────────────────────────────────────────
RANGE = {"date_from": "2026-06-01", "date_to": "2026-06-02"}

# Every read surface an executive (scope "all") must reach: GET path + query params.
EXECUTIVE_CAN_READ: list[tuple[str, dict[str, Any]]] = [
    ("/api/v1/metrics/summary", RANGE),
    ("/api/v1/metrics/timeseries", {**RANGE, "metrics": "total_revenue_usd"}),
    ("/api/v1/metrics/breakdown", {**RANGE, "group_by": "app", "metrics": "total_revenue_usd"}),
    ("/api/v1/metrics/table", {**RANGE, "sort": "total_revenue_usd"}),
    ("/api/v1/apps", {}),
    ("/api/v1/meta/freshness", {}),
    ("/api/v1/meta/targets", {"year": 2026}),
]

# Every write/admin surface that must be forbidden. The admin router and the
# share approve/reject routes gate on the admin_panel capability BEFORE any body
# or query validation, so dummy bodies/ids still yield 403 (not 404/422). The
# body (3rd field) is only sent for write methods; for get/delete it's ignored.
_DUMMY_ID = "00000000-0000-0000-0000-000000000000"
EXECUTIVE_FORBIDDEN: list[tuple[str, str, dict[str, Any]]] = [
    ("get", "/api/v1/admin/users", {}),  # manage users (list)
    ("post", "/api/v1/admin/users", {"email": "x@terafort.org", "roles": ["viewer"]}),
    ("patch", f"/api/v1/admin/users/{_DUMMY_ID}", {"is_active": False}),
    ("get", "/api/v1/admin/roles", {}),  # change settings (read config)
    ("put", f"/api/v1/admin/roles/{_DUMMY_ID}", {"metric_groups": [], "capabilities": []}),
    ("get", "/api/v1/admin/targets", {}),
    ("put", "/api/v1/admin/targets", {"period": "year", "target_usd": 1}),  # set targets
    ("delete", f"/api/v1/admin/targets/{_DUMMY_ID}", {}),  # remove targets
    ("get", "/api/v1/admin/audit", {}),
    ("get", "/api/v1/admin/data-health", {}),
    ("post", f"/api/v1/reports/shares/{_DUMMY_ID}/approve", {}),  # approve shares
    ("post", f"/api/v1/reports/shares/{_DUMMY_ID}/reject", {}),  # reject shares
]


async def test_executive_can_read_every_page(metrics_env: MetricsEnv) -> None:
    """An executive with scope 'all' has full read visibility across every page."""
    for path, params in EXECUTIVE_CAN_READ:
        resp = await metrics_env.client.get(path, params=params, headers=_auth("executive"))
        assert resp.status_code == 200, f"executive blocked from {path}: {resp.status_code}"


async def test_executive_sees_all_metric_groups(metrics_env: MetricsEnv) -> None:
    """Full metric visibility: store, spend, ad/iap revenue, profitability AND the
    attribution group (the latter is what separates full-visibility roles from
    marketing/finance). Nothing is filtered out for an executive."""
    resp = await metrics_env.client.get(
        "/api/v1/metrics/summary", params=RANGE, headers=_auth("executive")
    )
    assert resp.status_code == 200
    current = resp.json()["current"]
    for key in (
        "store_total_installs",
        "total_ua_spend_usd",
        "total_ad_revenue_usd",
        "total_iap_net_usd",
        "profit_usd",
        "adjust_installs",
    ):
        assert key in current, f"executive missing metric group column {key}"


async def test_executive_scope_all_sees_every_pod(metrics_env: MetricsEnv) -> None:
    """Scope 'all' = no row filtering: the executive sees both pods' data, unlike a
    pod-scoped user. Proves full data visibility, not just full column visibility."""
    resp = await metrics_env.client.get(
        "/api/v1/metrics/breakdown",
        params={**RANGE, "group_by": "pod", "metrics": "total_revenue_usd"},
        headers=_auth("executive"),
    )
    assert resp.status_code == 200
    pods = {row["pod"] for row in resp.json()["rows"]}
    assert {"POD_A", "POD_B"} <= pods


async def test_executive_cannot_write_or_admin(metrics_env: MetricsEnv) -> None:
    """No write/admin power: manage users, set targets, approve shares, change
    settings — every one returns 403 (missing admin_panel capability)."""
    for method, path, body in EXECUTIVE_FORBIDDEN:
        call = getattr(metrics_env.client, method)
        kwargs: dict[str, Any] = {"headers": _auth("executive")}
        if method in ("post", "put", "patch"):
            kwargs["json"] = body
        resp = await call(path, **kwargs)
        assert resp.status_code == 403, f"executive reached {method.upper()} {path}"


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

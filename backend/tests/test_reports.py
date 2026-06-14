"""Integration tests for Step 6: saved views, saved reports, and sharing.

Exercises per-user isolation, write-time column RBAC, the admin-approval share
lifecycle, recipient-side RBAC narrowing (scope + permitted metrics), and the
audit trail for every share/approve/reject.
"""

from typing import Any

from app.models import AuditLog
from sqlalchemy import select

from tests.conftest import MetricsEnv, _metrics_uid

RANGE: dict[str, Any] = {"date_from": "2026-06-01", "date_to": "2026-06-02"}


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def _report_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "Installs by app",
        "filters": dict(RANGE),
        "columns": ["store_total_installs", "total_revenue_usd"],
        "group_by": "app",
    }
    body.update(overrides)
    return body


async def _audit_actions(env: MetricsEnv) -> list[str]:
    async with env.sessionmaker() as session:
        rows = (await session.execute(select(AuditLog.action))).scalars().all()
    return list(rows)


# ── Directory (share-recipient picker) ───────────────────────────────────────
async def test_directory_excludes_self(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/auth/directory", headers=_auth("admin"))
    assert resp.status_code == 200
    ids = {entry["user_id"] for entry in resp.json()}
    assert _metrics_uid("admin") not in ids
    assert _metrics_uid("finance") in ids


# ── Saved views ──────────────────────────────────────────────────────────────
async def test_saved_views_are_per_user(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post(
        "/api/v1/views",
        json={"name": "My view", "page": "overview", "filters": RANGE},
        headers=_auth("admin"),
    )
    assert created.status_code == 201
    view_id = created.json()["id"]

    mine = await client.get("/api/v1/views", headers=_auth("admin"))
    assert [v["id"] for v in mine.json()] == [view_id]

    # A different user never sees it.
    other = await client.get("/api/v1/views", headers=_auth("executive"))
    assert other.json() == []

    # And cannot update or delete it (404, not 403).
    not_mine = await client.put(
        f"/api/v1/views/{view_id}",
        json={"name": "x", "page": "overview", "filters": RANGE},
        headers=_auth("executive"),
    )
    assert not_mine.status_code == 404

    deleted = await client.delete(f"/api/v1/views/{view_id}", headers=_auth("admin"))
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/views", headers=_auth("admin"))).json() == []


# ── Saved reports: CRUD + write-time column RBAC ─────────────────────────────
async def test_report_rejects_forbidden_column_on_write(metrics_env: MetricsEnv) -> None:
    # Viewer may only aggregate store_installs; total_revenue_usd is forbidden.
    resp = await metrics_env.client.post(
        "/api/v1/reports", json=_report_body(), headers=_auth("viewer")
    )
    assert resp.status_code == 400
    assert "total_revenue_usd" in resp.json()["error"]["message"]


async def test_report_create_and_owner_run(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("admin"))
    assert created.status_code == 201
    report_id = created.json()["id"]
    assert created.json()["is_owner"] is True

    run = await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("admin"))
    assert run.status_code == 200
    payload = run.json()
    assert payload["group_by"] == "app"
    assert set(payload["columns"]) == {"store_total_installs", "total_revenue_usd"}
    by_app = {row["app"]: row for row in payload["rows"]}
    assert by_app["appA"]["total_revenue_usd"] == 1000.0


async def test_other_user_cannot_see_report(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("admin"))
    report_id = created.json()["id"]

    assert (
        await client.get(f"/api/v1/reports/{report_id}", headers=_auth("executive"))
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("executive"))
    ).status_code == 404


# ── Sharing lifecycle ────────────────────────────────────────────────────────
async def test_nonadmin_share_is_pending_until_admin_approves(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    # Executive (no admin_panel) owns and shares a report with finance.
    created = await client.post(
        "/api/v1/reports", json=_report_body(name="Exec report"), headers=_auth("executive")
    )
    report_id = created.json()["id"]
    share = await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("finance")},
        headers=_auth("executive"),
    )
    assert share.status_code == 201
    assert share.json()["status"] == "pending"
    share_id = share.json()["id"]

    # Finance cannot see it yet.
    assert (
        await client.get("/api/v1/reports/shared-with-me", headers=_auth("finance"))
    ).json() == []
    assert (
        await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("finance"))
    ).status_code == 404

    # Admin sees the pending queue and approves.
    pending = await client.get("/api/v1/reports/shares/pending", headers=_auth("admin"))
    assert [s["id"] for s in pending.json()] == [share_id]
    approved = await client.post(
        f"/api/v1/reports/shares/{share_id}/approve", headers=_auth("admin")
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # Now finance sees and can run it.
    shared = await client.get("/api/v1/reports/shared-with-me", headers=_auth("finance"))
    assert [r["id"] for r in shared.json()] == [report_id]
    assert (
        await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("finance"))
    ).status_code == 200

    actions = await _audit_actions(metrics_env)
    assert "report_share" in actions
    assert "report_share_approved" in actions


async def test_admin_self_share_is_auto_approved(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("admin"))
    report_id = created.json()["id"]
    share = await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("executive")},
        headers=_auth("admin"),
    )
    assert share.status_code == 201
    assert share.json()["status"] == "approved"
    # No admin step needed: executive already sees it.
    shared = await client.get("/api/v1/reports/shared-with-me", headers=_auth("executive"))
    assert [r["id"] for r in shared.json()] == [report_id]


async def test_rejected_share_stays_invisible(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("executive"))
    report_id = created.json()["id"]
    share = await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("finance")},
        headers=_auth("executive"),
    )
    share_id = share.json()["id"]
    rejected = await client.post(
        f"/api/v1/reports/shares/{share_id}/reject", headers=_auth("admin")
    )
    assert rejected.json()["status"] == "rejected"
    assert (
        await client.get("/api/v1/reports/shared-with-me", headers=_auth("finance"))
    ).json() == []
    assert "report_share_rejected" in await _audit_actions(metrics_env)


async def test_viewer_cannot_share(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    # Viewer owns a (store_installs-only) report but lacks share_report capability.
    created = await client.post(
        "/api/v1/reports",
        json=_report_body(columns=["store_total_installs"]),
        headers=_auth("viewer"),
    )
    report_id = created.json()["id"]
    share = await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("admin")},
        headers=_auth("viewer"),
    )
    assert share.status_code == 403


async def test_non_owner_cannot_share(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("admin"))
    report_id = created.json()["id"]
    # Executive holds share_report but does not own the report -> 404.
    share = await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("finance")},
        headers=_auth("executive"),
    )
    assert share.status_code == 404


# ── Recipient-side RBAC narrowing on a shared report ─────────────────────────
async def test_recipient_metric_columns_are_narrowed(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("admin"))
    report_id = created.json()["id"]
    share = await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("viewer")},
        headers=_auth("admin"),
    )
    assert share.json()["status"] == "approved"

    run = await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("viewer"))
    payload = run.json()
    # Viewer keeps store_installs only; total_revenue_usd is stripped from the result.
    assert payload["columns"] == ["store_total_installs"]
    assert all("total_revenue_usd" not in row for row in payload["rows"])


async def test_recipient_row_scope_is_narrowed(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("admin"))
    report_id = created.json()["id"]
    await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("pod_owner_scoped")},
        headers=_auth("admin"),
    )

    run = await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("pod_owner_scoped"))
    apps = {row["app"] for row in run.json()["rows"]}
    # pod_owner_scoped only sees POD_A apps; appB (POD_B) is invisible.
    assert apps == {"appA", "appZ"}


async def test_revoke_cuts_off_access(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    created = await client.post("/api/v1/reports", json=_report_body(), headers=_auth("admin"))
    report_id = created.json()["id"]
    share = await client.post(
        f"/api/v1/reports/{report_id}/share",
        json={"shared_with": _metrics_uid("finance")},
        headers=_auth("admin"),
    )
    share_id = share.json()["id"]
    assert (
        await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("finance"))
    ).status_code == 200

    revoked = await client.post(f"/api/v1/reports/shares/{share_id}/revoke", headers=_auth("admin"))
    assert revoked.json()["status"] == "revoked"
    assert (
        await client.post(f"/api/v1/reports/{report_id}/run", headers=_auth("finance"))
    ).status_code == 404
    assert "report_share_revoked" in await _audit_actions(metrics_env)

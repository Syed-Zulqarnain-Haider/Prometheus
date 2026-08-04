"""Notifications: RBAC-scoped visibility + read state."""

from typing import Any

from app.models import Notification
from sqlalchemy import insert

from tests.conftest import MetricsEnv, _metrics_uid


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _seed(env: MetricsEnv) -> None:
    viewer_id = _metrics_uid("viewer")
    async with env.sessionmaker() as s:
        await s.execute(
            insert(Notification),
            [
                {"type": "t", "title": "everyone", "audience": "all"},
                {"type": "t", "title": "admins only", "audience": "admins"},
                {"type": "t", "title": "for viewer", "audience": f"user:{viewer_id}"},
            ],
        )
        await s.commit()


async def test_audience_scoping(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    c = metrics_env.client

    admin = (await c.get("/api/v1/notifications", headers=_auth("admin"))).json()
    titles_admin = {n["title"] for n in admin["items"]}
    assert "everyone" in titles_admin and "admins only" in titles_admin  # admin sees admin-routed

    viewer = (await c.get("/api/v1/notifications", headers=_auth("viewer"))).json()
    titles_viewer = {n["title"] for n in viewer["items"]}
    assert "everyone" in titles_viewer  # all-audience
    assert "for viewer" in titles_viewer  # addressed to this user
    assert "admins only" not in titles_viewer  # NOT visible to a non-admin


async def test_mark_read_and_unread_count(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    c = metrics_env.client

    before = (await c.get("/api/v1/notifications", headers=_auth("viewer"))).json()
    assert before["unread"] == 2  # everyone + for-viewer
    first_id = before["items"][0]["id"]

    assert (
        await c.post(f"/api/v1/notifications/{first_id}/read", headers=_auth("viewer"))
    ).status_code == 204
    after = (await c.get("/api/v1/notifications", headers=_auth("viewer"))).json()
    assert after["unread"] == 1
    assert next(n for n in after["items"] if n["id"] == first_id)["read"] is True

    assert (
        await c.post("/api/v1/notifications/read-all", headers=_auth("viewer"))
    ).status_code == 204
    assert (await c.get("/api/v1/notifications", headers=_auth("viewer"))).json()["unread"] == 0


# ── v2: severity + clickable link + hierarchy routing ────────────────────────────
async def test_severity_and_link_surface_in_api(metrics_env: MetricsEnv) -> None:
    async with metrics_env.sessionmaker() as s:
        await s.execute(
            insert(Notification),
            [
                {
                    "type": "sync_failed",
                    "title": "Sync crashed",
                    "audience": "admins",
                    "severity": "critical",
                    "link": "/admin?tab=integration",
                }
            ],
        )
        await s.commit()

    admin = (await metrics_env.client.get("/api/v1/notifications", headers=_auth("admin"))).json()
    item = next(n for n in admin["items"] if n["title"] == "Sync crashed")
    assert item["severity"] == "critical"
    assert item["link"] == "/admin?tab=integration"


async def test_notify_role_routes_to_pod_owners(metrics_env: MetricsEnv, monkeypatch: Any) -> None:
    """Hierarchy routing: notify_role('pod_owner') reaches pod-owner users, not others."""
    from app.services import notification_service

    # The service writes on its own session; point it at the test DB.
    monkeypatch.setattr(notification_service, "get_sessionmaker", lambda: metrics_env.sessionmaker)
    await notification_service.notify_role(
        "pod_owner", type="share_request", title="needs approval", link="/reports?tab=shares"
    )

    po = (await metrics_env.client.get("/api/v1/notifications", headers=_auth("pod_owner"))).json()
    assert any(
        n["title"] == "needs approval" and n["link"] == "/reports?tab=shares" for n in po["items"]
    )
    # A viewer (not a pod owner) must NOT receive it.
    viewer = (await metrics_env.client.get("/api/v1/notifications", headers=_auth("viewer"))).json()
    assert all(n["title"] != "needs approval" for n in viewer["items"])

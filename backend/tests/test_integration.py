"""Integration tests for the admin Integration tab (PR 1 — foundation).

Covers: admin-only access (others 403); the composed status (BigQuery key presence +
Postgres/Redis health + last-sync history) that never leaks a credential; the
NON-SECRET integration settings (typed allowlist with format validation + group); the
read-only BigQuery 'Test Connection' being honest when the key is absent, audited, and
rate-limited; and that the integration keys are NOT client-readable.
"""

import json
from typing import Any

from app.models import AuditLog
from sqlalchemy import select

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


# ── Admin-only access ────────────────────────────────────────────────────────
async def test_integration_endpoints_require_admin(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    for method, path in [
        ("get", "/api/v1/admin/integration/status"),
        ("post", "/api/v1/admin/integration/test-bigquery"),
    ]:
        for role in ("viewer", "finance", "marketing"):
            resp = await getattr(c, method)(path, headers=_auth(role))
            assert resp.status_code == 403, f"{role} reached {method.upper()} {path}"


# ── Status: connections + sync history, never a credential ───────────────────
async def test_integration_status_reports_status_no_secrets(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/admin/integration/status", headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()

    assert body["postgres"]["status"] == "up"
    assert body["redis"]["status"] == "up"
    # No BigQuery reader key mounted in the test env → honest "not configured".
    assert body["bigquery"]["status"] == "not_configured"

    # Last-sync history surfaces the seeded successful run (status, rows, "data as of").
    assert body["last_sync"]["status"] == "success"
    assert body["last_sync"]["rows_loaded"] == 100
    assert body["last_sync"]["bq_built_at"] is not None
    assert isinstance(body["recent_syncs"], list) and len(body["recent_syncs"]) == 1

    # No connection string, credential, or key path anywhere in the payload.
    blob = json.dumps(body)
    for needle in ("postgresql://", "redis://", "rediss://", "password", "://", "/secrets/"):
        assert needle not in blob, f"integration status leaked '{needle}'"


# ── Integration settings: typed allowlist, group, defaults ───────────────────
async def test_integration_settings_have_group_and_defaults(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/admin/settings", headers=_auth("admin"))
    assert resp.status_code == 200
    by_key = {s["key"]: s for s in resp.json()}

    for key in ("gcp_project", "bq_view", "sync_enabled", "sync_schedule_time", "sync_timezone"):
        assert by_key[key]["group"] == "integration", f"{key} not grouped as integration"

    assert by_key["gcp_project"]["value"] == ""
    assert by_key["bq_view"]["value"] == "terafort.api.daily_performance_v1"
    assert by_key["sync_enabled"]["value"] is False
    assert by_key["sync_schedule_time"]["value"] == "06:00"
    assert by_key["sync_timezone"]["value"] == "UTC"
    # The general (System) settings keep their group too.
    assert by_key["data_freshness_threshold_hours"]["group"] == "general"


async def test_integration_settings_accept_valid_values_and_audit(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    valid = {
        "gcp_project": "my-project-123",
        "bq_view": "proj.dataset.daily_v2",
        "sync_enabled": True,
        "sync_schedule_time": "07:30",
        "sync_timezone": "America/New_York",
    }
    for key, value in valid.items():
        put = await c.put(
            f"/api/v1/admin/settings/{key}", json={"value": value}, headers=_auth("admin")
        )
        assert put.status_code == 200, f"{key}={value!r} rejected"
        assert put.json()["value"] == value

    # gcp_project may be cleared (empty == "not configured yet").
    cleared = await c.put(
        "/api/v1/admin/settings/gcp_project", json={"value": ""}, headers=_auth("admin")
    )
    assert cleared.status_code == 200
    assert cleared.json()["value"] == ""

    # Persisted + audited.
    got = await c.get("/api/v1/admin/settings", headers=_auth("admin"))
    by_key = {s["key"]: s for s in got.json()}
    assert by_key["bq_view"]["value"] == "proj.dataset.daily_v2"
    assert by_key["sync_enabled"]["value"] is True

    async with metrics_env.sessionmaker() as session:
        stmt = select(AuditLog.action).where(AuditLog.action == "admin_update_setting")
        actions = (await session.execute(stmt)).scalars().all()
    assert "admin_update_setting" in actions


async def test_integration_settings_reject_bad_formats_and_secrets(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    bad = {
        "sync_schedule_time": "25:61",  # not a valid HH:MM
        "sync_timezone": "Mars/Phobos",  # not a real IANA tz
        "bq_view": "no_dots_here",  # not a qualified view
        "gcp_project": "BadCaps_Project!",  # invalid project id
    }
    for key, value in bad.items():
        resp = await c.put(
            f"/api/v1/admin/settings/{key}", json={"value": value}, headers=_auth("admin")
        )
        assert resp.status_code == 400, f"{key}={value!r} should be rejected"

    # A connection string can never masquerade as a view (proves no-secret guarantee).
    dsn = await c.put(
        "/api/v1/admin/settings/bq_view",
        json={"value": "postgresql://user:pass@host:5432/db"},
        headers=_auth("admin"),
    )
    assert dsn.status_code == 400

    # A long blob (e.g. a pasted key) is rejected outright.
    blob = await c.put(
        "/api/v1/admin/settings/gcp_project",
        json={"value": "x" * 300},
        headers=_auth("admin"),
    )
    assert blob.status_code == 400

    # A bool setting cannot accept an arbitrary string.
    wrong_type = await c.put(
        "/api/v1/admin/settings/sync_enabled", json={"value": "yes"}, headers=_auth("admin")
    )
    assert wrong_type.status_code == 400


# ── Integration keys are admin-only (never client-readable) ──────────────────
async def test_integration_keys_not_client_readable(metrics_env: MetricsEnv) -> None:
    body = (await metrics_env.client.get("/api/v1/meta/settings", headers=_auth("viewer"))).json()
    for key in ("gcp_project", "bq_view", "sync_enabled", "sync_schedule_time", "sync_timezone"):
        assert key not in body, f"client settings leaked integration key '{key}'"


# ── Test Connection: honest when no key, audited ─────────────────────────────
async def test_test_bigquery_honest_when_no_key(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        "/api/v1/admin/integration/test-bigquery", headers=_auth("admin")
    )
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    assert body["ok"] is False
    assert "key" in body["message"].lower()  # honest: points at the missing key
    # No credential / key path leaked in the sanitized message.
    for needle in ("/secrets/", "postgresql://", "password"):
        assert needle not in body["message"]

    async with metrics_env.sessionmaker() as session:
        stmt = select(AuditLog.action).where(AuditLog.action == "admin_test_bigquery")
        actions = (await session.execute(stmt)).scalars().all()
    assert "admin_test_bigquery" in actions


async def test_test_bigquery_is_rate_limited(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    for _ in range(3):  # SYNC_RATE_LIMIT = 3 / min (shared tight bucket)
        ok = await c.post("/api/v1/admin/integration/test-bigquery", headers=_auth("admin"))
        assert ok.status_code == 200
    blocked = await c.post("/api/v1/admin/integration/test-bigquery", headers=_auth("admin"))
    assert blocked.status_code == 429

"""Tests for the admin App Master feature (Postgres serving copy of BigQuery app_master_v2).

Admin-only throughout; edits touch only the owner-approved editable columns, write to
BigQuery FIRST (mocked here — no GCP in tests) then Postgres, and are audited. The
BigQuery read/write functions are monkeypatched; the Postgres + RBAC + audit paths are real.
"""

from typing import Any

import pytest
from app.core.app_master_columns import ALL_COLUMNS, EDITABLE_SET
from app.models.app_master import APP_MASTER_TABLE
from app.services import app_master_bq
from sqlalchemy import insert, select

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _seed(env: MetricsEnv) -> None:
    async with env.sessionmaker() as s:
        await s.execute(
            insert(APP_MASTER_TABLE),
            [
                {
                    "canonical_key": "app-a",
                    "app_name": "Alpha",
                    "platform": "ios",
                    "publisher": "PubA",
                    "hou": "H1",
                    "pod": 1,
                    "needs_review": False,
                    "revenue_share_pct": 1.0,
                },
                {
                    "canonical_key": "app-b",
                    "app_name": "Beta",
                    "platform": "android",
                    "publisher": "PubB",
                    "hou": "H2",
                    "pod": 2,
                    "needs_review": True,
                    "revenue_share_pct": 0.5,
                },
            ],
        )
        await s.commit()


# ── column registry / model parity ──────────────────────────────────────────────
def test_model_matches_column_registry() -> None:
    assert set(APP_MASTER_TABLE.columns.keys()) == set(ALL_COLUMNS)
    # canonical_key is the PK and is NOT editable.
    assert "canonical_key" not in EDITABLE_SET
    assert [c.name for c in APP_MASTER_TABLE.primary_key.columns] == ["canonical_key"]


# ── RBAC: admin-only ────────────────────────────────────────────────────────────
async def test_app_master_requires_admin(metrics_env: MetricsEnv) -> None:
    c = metrics_env.client
    for role in ("viewer", "executive", "finance", "marketing", "pod_owner"):
        assert (await c.get("/api/v1/app-master", headers=_auth(role))).status_code == 403
        assert (
            await c.patch("/api/v1/app-master/app-a", json={"hou": "H9"}, headers=_auth(role))
        ).status_code == 403
        assert (await c.post("/api/v1/app-master/refresh", headers=_auth(role))).status_code == 403


# ── list + separate filters ─────────────────────────────────────────────────────
async def test_list_returns_rows_columns_and_editability(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    resp = await metrics_env.client.get("/api/v1/app-master", headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["primary_key"] == "canonical_key"
    assert {r["canonical_key"] for r in body["rows"]} == {"app-a", "app-b"}
    editable = {c["name"] for c in body["columns"] if c["editable"]}
    assert "hou" in editable and "publisher" in editable
    assert "canonical_key" not in editable and "apple_id" not in editable


async def test_list_filters(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    c = metrics_env.client

    ios = (await c.get("/api/v1/app-master?platform=ios", headers=_auth("admin"))).json()
    assert [r["canonical_key"] for r in ios["rows"]] == ["app-a"]

    review = (await c.get("/api/v1/app-master?needs_review=true", headers=_auth("admin"))).json()
    assert [r["canonical_key"] for r in review["rows"]] == ["app-b"]

    search = (await c.get("/api/v1/app-master?search=Beta", headers=_auth("admin"))).json()
    assert [r["canonical_key"] for r in search["rows"]] == ["app-b"]

    hou = (await c.get("/api/v1/app-master?hou=H1", headers=_auth("admin"))).json()
    assert [r["canonical_key"] for r in hou["rows"]] == ["app-a"]


# ── edit: BigQuery-first write-back, then Postgres, audited ──────────────────────
async def test_edit_writes_bigquery_then_postgres_and_audits(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(metrics_env)
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_push(settings: Any, key: str, changes: dict[str, Any]) -> None:
        calls.append((key, changes))

    monkeypatch.setattr(app_master_bq, "push_update", fake_push)

    resp = await metrics_env.client.patch(
        "/api/v1/app-master/app-a",
        json={"hou": "H9", "needs_review": True, "revenue_share_pct": 0.75},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    assert resp.json()["hou"] == "H9"

    # BigQuery was called with exactly the changed editable columns.
    assert calls == [("app-a", {"hou": "H9", "needs_review": True, "revenue_share_pct": 0.75})]

    # Postgres serving copy reflects the change.
    async with metrics_env.sessionmaker() as s:
        row = (
            (
                await s.execute(
                    select(APP_MASTER_TABLE).where(APP_MASTER_TABLE.c.canonical_key == "app-a")
                )
            )
            .mappings()
            .one()
        )
    assert row["hou"] == "H9" and row["needs_review"] is True

    # Audited.
    async with metrics_env.sessionmaker() as s:
        from app.models import AuditLog

        actions = (
            (
                await s.execute(
                    select(AuditLog.action).where(AuditLog.action == "admin_edit_app_master")
                )
            )
            .scalars()
            .all()
        )
    assert "admin_edit_app_master" in actions


async def test_edit_rejects_non_editable_or_unknown_columns(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    c = metrics_env.client
    # apple_id is read-only; xyz is unknown — both rejected by the schema (extra=forbid).
    assert (
        await c.patch("/api/v1/app-master/app-a", json={"apple_id": 5}, headers=_auth("admin"))
    ).status_code == 422
    assert (
        await c.patch("/api/v1/app-master/app-a", json={"xyz": 1}, headers=_auth("admin"))
    ).status_code == 422


async def test_edit_unknown_key_404(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_master_bq, "push_update", lambda *a, **k: None)
    resp = await metrics_env.client.patch(
        "/api/v1/app-master/does-not-exist", json={"hou": "H9"}, headers=_auth("admin")
    )
    assert resp.status_code == 404


async def test_edit_leaves_postgres_untouched_when_bigquery_write_fails(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(metrics_env)

    def boom(settings: Any, key: str, changes: dict[str, Any]) -> None:
        raise app_master_bq.BigQueryNotConfigured("no writer key")

    monkeypatch.setattr(app_master_bq, "push_update", boom)

    resp = await metrics_env.client.patch(
        "/api/v1/app-master/app-a", json={"hou": "H9"}, headers=_auth("admin")
    )
    assert resp.status_code == 503
    # The serving copy is unchanged — BigQuery is written FIRST, so a failure changes nothing.
    async with metrics_env.sessionmaker() as s:
        row = (
            (
                await s.execute(
                    select(APP_MASTER_TABLE).where(APP_MASTER_TABLE.c.canonical_key == "app-a")
                )
            )
            .mappings()
            .one()
        )
    assert row["hou"] == "H1"


# ── refresh from BigQuery ────────────────────────────────────────────────────────
async def test_refresh_replaces_serving_copy_and_skips_keyless_rows(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(metrics_env)

    def fake_fetch(settings: Any) -> list[dict[str, Any]]:
        base = dict.fromkeys(ALL_COLUMNS)
        return [
            {**base, "canonical_key": "app-c", "app_name": "Gamma", "platform": "ios"},
            {**base, "canonical_key": None, "app_name": "NoKey"},  # skipped (no key)
        ]

    monkeypatch.setattr(app_master_bq, "fetch_rows", fake_fetch)

    resp = await metrics_env.client.post("/api/v1/app-master/refresh", headers=_auth("admin"))
    assert resp.status_code == 200
    assert resp.json() == {"synced": 1, "skipped": 1}

    # Full refresh: old rows gone, only the keyed fetched row remains.
    listing = (await metrics_env.client.get("/api/v1/app-master", headers=_auth("admin"))).json()
    assert [r["canonical_key"] for r in listing["rows"]] == ["app-c"]

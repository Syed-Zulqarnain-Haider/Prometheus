"""Tests for the admin App Master feature (Postgres serving copy of BigQuery app_master_v2).

Admin-only throughout; edits touch only the owner-approved editable columns, write to
BigQuery FIRST (mocked here — no GCP in tests) then Postgres, and are audited. The
BigQuery read/write functions are monkeypatched; the Postgres + RBAC + audit paths are real.
"""

from typing import Any

import pytest
from app.core.app_master_columns import ALL_COLUMNS, EDITABLE_SET, REGISTRY
from app.models.app_master import APP_MASTER_TABLE
from app.services import app_master_bq, app_master_service, integration_service
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

    def fake_push(settings: Any, table_id: str, key: str, changes: dict[str, Any]) -> None:
        calls.append((key, changes))

    monkeypatch.setattr(app_master_bq, "push_update", fake_push)

    resp = await metrics_env.client.patch(
        "/api/v1/app-master/app-a",
        json={"hou": "H9", "partner_name": "Acme", "pod_owner": "Neo"},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    assert resp.json()["hou"] == "H9"

    # BigQuery was called with exactly the changed editable columns.
    assert calls == [("app-a", {"hou": "H9", "partner_name": "Acme", "pod_owner": "Neo"})]

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
    assert row["hou"] == "H9" and row["partner_name"] == "Acme"

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


async def test_edit_validates_pod_and_net_revenue_share(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    c = metrics_env.client
    # pod must be > 0.
    assert (
        await c.patch("/api/v1/app-master/app-a", json={"pod": 0}, headers=_auth("admin"))
    ).status_code == 422
    assert (
        await c.patch("/api/v1/app-master/app-a", json={"pod": -3}, headers=_auth("admin"))
    ).status_code == 422
    # net_revenue_share must be within [0.0, 1.0].
    assert (
        await c.patch(
            "/api/v1/app-master/app-a", json={"net_revenue_share": 1.5}, headers=_auth("admin")
        )
    ).status_code == 422
    assert (
        await c.patch(
            "/api/v1/app-master/app-a", json={"net_revenue_share": -0.1}, headers=_auth("admin")
        )
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

    def boom(settings: Any, table_id: str, key: str, changes: dict[str, Any]) -> None:
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

    def fake_fetch(
        settings: Any, table_id: str, extra_columns: list[str] | None = None
    ) -> list[dict[str, Any]]:
        base = dict.fromkeys(ALL_COLUMNS)
        return [
            {**base, "canonical_key": "app-c", "app_name": "Gamma", "platform": "ios"},
            {**base, "canonical_key": None, "app_name": "NoKey"},  # skipped (no key)
        ]

    monkeypatch.setattr(app_master_bq, "fetch_rows", fake_fetch)

    resp = await metrics_env.client.post("/api/v1/app-master/refresh", headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 1 and body["skipped"] == 1
    # app-c wasn't in the seeded master → detected as a NEW app (alerts admins to set HOU/pod/rev).
    assert body["new_apps"] == [{"canonical_key": "app-c", "app_name": "Gamma", "platform": "ios"}]

    # Full refresh: old rows gone, only the keyed fetched row remains.
    listing = (await metrics_env.client.get("/api/v1/app-master", headers=_auth("admin"))).json()
    assert [r["canonical_key"] for r in listing["rows"]] == ["app-c"]


async def test_new_apps_alert_emails_admins(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A newly-discovered app emails the admins (best-effort) to set HOU/pod/net-revenue."""
    from app.services import email_service

    await _seed(metrics_env)

    def fake_fetch(
        settings: Any, table_id: str, extra_columns: list[str] | None = None
    ) -> list[dict[str, Any]]:
        base = dict.fromkeys(ALL_COLUMNS)
        return [{**base, "canonical_key": "app-new", "app_name": "Fresh", "platform": "android"}]

    monkeypatch.setattr(app_master_bq, "fetch_rows", fake_fetch)

    sent: list[tuple[list[str], str]] = []

    async def fake_send(settings: Any, recipients: list[str], subject: str, body: str) -> bool:
        sent.append((recipients, subject))
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)

    resp = await metrics_env.client.post("/api/v1/app-master/refresh", headers=_auth("admin"))
    assert resp.status_code == 200
    assert resp.json()["new_apps"][0]["canonical_key"] == "app-new"

    assert sent, "expected an admin email for the newly-discovered app"
    recipients, subject = sent[0]
    assert recipients and "new app" in subject.lower()


async def test_refresh_db_write_failure_is_sanitized_not_500(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A serving-copy write failure must surface as a sanitized 502 (existing data kept),
    never a blind 500."""
    await _seed(metrics_env)

    def fake_fetch(
        settings: Any, table_id: str, extra_columns: list[str] | None = None
    ) -> list[dict[str, Any]]:
        base = dict.fromkeys(ALL_COLUMNS)
        # A pod value that can't go into the bigint column -> DB write fails.
        return [{**base, "canonical_key": "bad", "platform": "ios", "pod": "not-an-int"}]

    monkeypatch.setattr(app_master_bq, "fetch_rows", fake_fetch)

    resp = await metrics_env.client.post("/api/v1/app-master/refresh", headers=_auth("admin"))
    assert resp.status_code == 502
    assert "existing data" in resp.json()["error"]["message"].lower()
    # The pre-existing serving rows are still intact (write rolled back).
    listing = (await metrics_env.client.get("/api/v1/app-master", headers=_auth("admin"))).json()
    assert {r["canonical_key"] for r in listing["rows"]} == {"app-a", "app-b"}


# ── schema match (verify a configured BigQuery table's columns) ──────────────────
async def test_schema_diff_reports_match(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_master_service, "_key_present", lambda _p: True)
    exact = {c.bq_name: c.bq_type for c in REGISTRY}

    def fake_run(key_path: str, project: str, table: str) -> tuple[dict[str, str] | None, None]:
        return (exact, None)

    monkeypatch.setattr(integration_service, "_run_schema_diff", fake_run)
    resp = await metrics_env.client.get("/api/v1/app-master/schema-diff", headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["in_sync"] is True
    assert body["missing_in_view"] == [] and body["type_mismatches"] == []


async def test_schema_diff_matches_case_insensitively(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    # BigQuery reports column names in a different case than our bq_name — e.g. the real column
    # is "net revenue share" while the registry's bq_name is "Net Revenue Share". This must NOT
    # be reported as both missing AND unregistered (the "Not in BigQuery / Skipped" bug).
    monkeypatch.setattr(app_master_service, "_key_present", lambda _p: True)
    actual = {c.bq_name.lower(): c.bq_type for c in REGISTRY}  # every BQ name lowercased

    def fake_run(key_path: str, project: str, table: str) -> tuple[dict[str, str] | None, None]:
        return (actual, None)

    monkeypatch.setattr(integration_service, "_run_schema_diff", fake_run)
    body = (
        await metrics_env.client.get("/api/v1/app-master/schema-diff", headers=_auth("admin"))
    ).json()
    assert body["in_sync"] is True
    assert body["missing_in_view"] == []
    assert body["unregistered_in_view"] == []


async def test_schema_diff_flags_missing_and_mismatch(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_master_service, "_key_present", lambda _p: True)
    actual = {c.bq_name: c.bq_type for c in REGISTRY}
    actual.pop("hou")  # a column the registry expects is missing from the table
    actual["publisher"] = "INT64"  # wrong type (registry says STRING)
    actual["surprise_col"] = "STRING"  # an extra column the registry doesn't map

    def fake_run(key_path: str, project: str, table: str) -> tuple[dict[str, str] | None, None]:
        return (actual, None)

    monkeypatch.setattr(integration_service, "_run_schema_diff", fake_run)
    body = (
        await metrics_env.client.get("/api/v1/app-master/schema-diff", headers=_auth("admin"))
    ).json()
    assert body["in_sync"] is False
    assert "hou" in body["missing_in_view"]
    assert any(m["column"] == "publisher" for m in body["type_mismatches"])
    assert any(u["column"] == "surprise_col" for u in body["unregistered_in_view"])


async def test_schema_diff_requires_admin(metrics_env: MetricsEnv) -> None:
    for role in ("viewer", "executive", "finance"):
        resp = await metrics_env.client.get("/api/v1/app-master/schema-diff", headers=_auth(role))
        assert resp.status_code == 403


# ── new filters: publisher (multi), package, app_id ──────────────────────────────
async def test_list_new_filters(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    async with metrics_env.sessionmaker() as s:
        await s.execute(
            insert(APP_MASTER_TABLE),
            [
                {
                    "canonical_key": "app-c",
                    "app_name": "Gamma",
                    "platform": "ios",
                    "publisher": "PubA",
                    "android_package": "com.acme.gamma",
                    "apple_id": 12345,
                }
            ],
        )
        await s.commit()
    c = metrics_env.client
    # publisher multi-select (repeated param) → PubA matches app-a + app-c
    r = (
        await c.get("/api/v1/app-master?publisher=PubA&publisher=PubB", headers=_auth("admin"))
    ).json()
    assert {row["canonical_key"] for row in r["rows"]} == {"app-a", "app-b", "app-c"}
    r = (await c.get("/api/v1/app-master?publisher=PubA", headers=_auth("admin"))).json()
    assert {row["canonical_key"] for row in r["rows"]} == {"app-a", "app-c"}
    # package substring
    r = (await c.get("/api/v1/app-master?package=acme", headers=_auth("admin"))).json()
    assert [row["canonical_key"] for row in r["rows"]] == ["app-c"]
    # app_id substring (matches apple_id or canonical_key)
    r = (await c.get("/api/v1/app-master?app_id=12345", headers=_auth("admin"))).json()
    assert [row["canonical_key"] for row in r["rows"]] == ["app-c"]


async def test_filter_by_last_synced_at_range(metrics_env: MetricsEnv) -> None:
    from datetime import UTC, datetime

    async with metrics_env.sessionmaker() as s:
        await s.execute(
            insert(APP_MASTER_TABLE),
            [
                {
                    "canonical_key": "sync-old",
                    "app_name": "Old",
                    "platform": "ios",
                    "last_synced_at": datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
                },
                {
                    "canonical_key": "sync-new",
                    "app_name": "New",
                    "platform": "ios",
                    "last_synced_at": datetime(2026, 6, 15, 9, 0, tzinfo=UTC),
                },
            ],
        )
        await s.commit()
    c = metrics_env.client

    async def keys(qs: str) -> set[str]:
        body = (await c.get(f"/api/v1/app-master?{qs}", headers=_auth("admin"))).json()
        return {r["canonical_key"] for r in body["rows"]}

    # from-bound excludes the older row; to-bound excludes the newer; the range includes both.
    assert await keys("synced_from=2026-06-10") == {"sync-new"}
    assert await keys("synced_to=2026-06-10") == {"sync-old"}
    # to-bound is inclusive of the whole day (last_synced_at at 09:00 on the 15th is included).
    both = await keys("synced_from=2026-06-01&synced_to=2026-06-15")
    assert {"sync-old", "sync-new"} <= both


async def test_filter_values(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    body = (
        await metrics_env.client.get("/api/v1/app-master/filter-values", headers=_auth("admin"))
    ).json()
    assert set(body["platforms"]) == {"ios", "android"}
    assert set(body["publishers"]) == {"PubA", "PubB"}
    assert set(body["pods"]) == {1, 2}


# ── global column order (admin-set, everyone sees it) ────────────────────────────
async def test_column_order_is_global_and_admin_only(metrics_env: MetricsEnv) -> None:
    await _seed(metrics_env)
    c = metrics_env.client
    new_order = ["hou", "publisher", "app_name"]  # partial; the rest append
    # non-admin cannot set it
    assert (
        await c.put(
            "/api/v1/app-master/column-order", json={"order": new_order}, headers=_auth("viewer")
        )
    ).status_code == 403
    # admin sets it
    resp = await c.put(
        "/api/v1/app-master/column-order", json={"order": new_order}, headers=_auth("admin")
    )
    assert resp.status_code == 200
    assert resp.json()[:3] == new_order
    assert set(resp.json()) == set(ALL_COLUMNS)  # covers every column
    # it now drives the list response's column order (global)
    listing = (await c.get("/api/v1/app-master", headers=_auth("admin"))).json()
    assert [col["name"] for col in listing["columns"]][:3] == new_order
    assert listing["column_order"][:3] == new_order


# ── undo + change history ────────────────────────────────────────────────────────
async def test_edit_records_history_and_undo_restores(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(metrics_env)
    monkeypatch.setattr(app_master_bq, "push_update", lambda *a, **k: None)
    c = metrics_env.client

    # edit hou H1 -> H9
    await c.patch("/api/v1/app-master/app-a", json={"hou": "H9"}, headers=_auth("admin"))
    hist = (await c.get("/api/v1/app-master/app-a/history", headers=_auth("admin"))).json()
    assert hist[0]["action"] == "edit"
    assert hist[0]["before"] == {"hou": "H1"} and hist[0]["after"] == {"hou": "H9"}
    assert hist[0]["editor_email"]  # attributed to the admin

    # undo -> back to H1
    undo = await c.post("/api/v1/app-master/app-a/undo", headers=_auth("admin"))
    assert undo.status_code == 200
    assert undo.json()["hou"] == "H1"
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
    # history now shows the undo on top; a second undo finds nothing
    hist = (await c.get("/api/v1/app-master/app-a/history", headers=_auth("admin"))).json()
    assert hist[0]["action"] == "undo"
    assert (
        await c.post("/api/v1/app-master/app-a/undo", headers=_auth("admin"))
    ).status_code == 404


async def test_undo_requires_admin(metrics_env: MetricsEnv) -> None:
    assert (
        await metrics_env.client.post("/api/v1/app-master/app-a/undo", headers=_auth("viewer"))
    ).status_code == 403

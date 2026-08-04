"""Tests for the admin "Match Database & BigQuery Schema" reconcile (App Master + fact table).

Covers the security-critical invariant: a BigQuery-discovered dynamic fact column is
``unclassified`` and is served to ADMINS ONLY — never to a non-admin role. Also covers the
additive/non-destructive reconcile mechanics and the type/identifier allow-list. BigQuery is
mocked (no GCP in tests); the Postgres + RBAC + audit paths are real.
"""

from typing import Any

import pytest
from app.core import metric_registry
from app.core.metric_registry import Col, Group, effective_registry, set_dynamic_columns
from app.models.dynamic_columns import DynamicColumn
from app.services import (
    fact_schema,
    integration_service,
    query_builder,
    schema_reconcile,
)
from app.services.response_models import build_response_model, permitted_columns
from sqlalchemy import insert, select

from tests.conftest import MetricsEnv

from .test_app_master import _auth, _seed


@pytest.fixture(autouse=True)
def _reset_dynamic_registry() -> Any:
    """Keep the module-level effective registry from leaking dynamic columns across tests."""
    yield
    set_dynamic_columns([])
    build_response_model.cache_clear()
    fact_schema._last_refresh = 0.0


# ── pure unit: type mapping + identifier guard ───────────────────────────────────
def test_map_bq_type_allow_list() -> None:
    assert schema_reconcile.map_bq_type("STRING") == "TEXT"
    assert schema_reconcile.map_bq_type("INT64") == "BIGINT"
    assert schema_reconcile.map_bq_type("FLOAT64") == "DOUBLE PRECISION"
    assert schema_reconcile.map_bq_type("NUMERIC(10, 2)") == "NUMERIC(38,9)"
    assert schema_reconcile.map_bq_type("BOOL") == "BOOLEAN"
    assert schema_reconcile.map_bq_type("TIMESTAMP") == "TIMESTAMPTZ"
    # Unsupported complex types are rejected (skipped + reported, never coerced).
    assert schema_reconcile.map_bq_type("ARRAY<INT64>") is None
    assert schema_reconcile.map_bq_type("STRUCT<a INT64>") is None
    assert schema_reconcile.map_bq_type("GEOGRAPHY") is None


def test_identifier_guard() -> None:
    assert schema_reconcile._IDENT_RE.match("new_metric_2")
    assert not schema_reconcile._IDENT_RE.match("Bad Name")
    assert not schema_reconcile._IDENT_RE.match("1leading_digit")
    assert not schema_reconcile._IDENT_RE.match("drop;table")


# ── SECURITY: a dynamic (unclassified) column reaches admins ONLY ────────────────
def test_unclassified_dynamic_column_is_admin_only() -> None:
    set_dynamic_columns([Col("secret_new_metric", "FLOAT64", "NUMERIC(18,4)", Group.UNCLASSIFIED)])
    build_response_model.cache_clear()

    admin_groups = frozenset(
        {
            Group.STORE_INSTALLS,
            Group.UA_SPEND,
            Group.AD_REVENUE,
            Group.IAP_REVENUE,
            Group.ATTRIBUTION,
            Group.PROFITABILITY,
            Group.UNCLASSIFIED,
        }
    )
    viewer_groups = frozenset({Group.STORE_INSTALLS})

    admin_cols = {c.name for c in permitted_columns(admin_groups)}
    viewer_cols = {c.name for c in permitted_columns(viewer_groups)}
    assert "secret_new_metric" in admin_cols
    assert "secret_new_metric" not in viewer_cols

    # And the generated Pydantic models agree — the field literally does not exist for viewer.
    assert "secret_new_metric" in build_response_model(admin_groups).model_fields
    assert "secret_new_metric" not in build_response_model(viewer_groups).model_fields


def test_dynamic_numeric_column_is_additive_measure() -> None:
    set_dynamic_columns([Col("new_kpi", "FLOAT64", "NUMERIC(18,4)", Group.UNCLASSIFIED)])
    assert "new_kpi" in query_builder.additive_measures()
    # A text dynamic column is NOT an additive measure.
    set_dynamic_columns([Col("new_label", "STRING", "TEXT", Group.UNCLASSIFIED)])
    assert "new_label" not in query_builder.additive_measures()


# ── App Master reconcile (admin-only feature, additive + non-destructive) ─────────
async def test_app_master_schema_sync_adds_and_skips(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(metrics_env)
    monkeypatch.setattr(integration_service, "_bq_key_present", lambda _s: True)

    from app.core.app_master_columns import REGISTRY as AM_REGISTRY

    actual = {c.bq_name: c.bq_type for c in AM_REGISTRY}
    actual["extra_metric"] = "FLOAT64"  # new, adoptable
    actual["Bad Name"] = "STRING"  # unsafe identifier -> skipped
    actual["blob_col"] = "STRUCT<a INT64>"  # unsupported type -> skipped

    def fake_run(key_path: str, project: str, table: str) -> tuple[dict[str, str] | None, None]:
        return (actual, None)

    monkeypatch.setattr(integration_service, "_run_schema_diff", fake_run)

    resp = await metrics_env.client.post("/api/v1/app-master/schema-sync", headers=_auth("admin"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True and body["ok"] is True
    assert [c["name"] for c in body["added"]] == ["extra_metric"]
    assert body["added"][0]["type"] == "DOUBLE PRECISION"
    skipped = {c["name"] for c in body["unsupported_types"]}
    assert "bad name" in skipped or "Bad Name" in skipped  # lowercased before matching
    assert "blob_col" in skipped
    # net_revenue_share's real BigQuery name has spaces ("Net Revenue Share") — it must be
    # recognised as the KNOWN static column via its bq_name alias, NOT skipped as an unsafe
    # name nor flagged missing (the "Skipped (unsupported): net revenue share" bug).
    assert "net revenue share" not in skipped
    assert "net_revenue_share" not in body["missing_in_bigquery"]

    # The dynamic column is now persisted and served (read-only) in the grid.
    async with metrics_env.sessionmaker() as s:
        rows = (
            (await s.execute(select(DynamicColumn).where(DynamicColumn.table_kind == "app_master")))
            .scalars()
            .all()
        )
    assert [r.name for r in rows] == ["extra_metric"]

    listing = (await metrics_env.client.get("/api/v1/app-master", headers=_auth("admin"))).json()
    col_meta = {c["name"]: c for c in listing["columns"]}
    assert "extra_metric" in col_meta
    assert col_meta["extra_metric"]["editable"] is False


async def test_app_master_schema_sync_requires_admin(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post("/api/v1/app-master/schema-sync", headers=_auth("viewer"))
    assert resp.status_code == 403


# ── Fact-table reconcile (adds admin-only dynamic columns) ────────────────────────
async def test_fact_schema_sync_adds_unclassified_column(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(integration_service, "_bq_key_present", lambda _s: True)

    actual = {c.name: c.bq_type for c in metric_registry.REGISTRY}
    actual["new_kpi"] = "FLOAT64"  # a brand-new BigQuery metric column

    def fake_run(key_path: str, project: str, view: str) -> tuple[dict[str, str] | None, None]:
        return (actual, None)

    monkeypatch.setattr(integration_service, "_run_schema_diff", fake_run)

    resp = await metrics_env.client.post(
        "/api/v1/admin/integration/schema-sync", headers=_auth("admin")
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert [c["name"] for c in body["added"]] == ["new_kpi"]

    # Persisted as a fact dynamic column, adopted into the effective registry as unclassified,
    # and now a summable measure — for the admin (unclassified) group only.
    async with metrics_env.sessionmaker() as s:
        rows = (
            (await s.execute(select(DynamicColumn).where(DynamicColumn.table_kind == "fact")))
            .scalars()
            .all()
        )
    assert [(r.name, r.active) for r in rows] == [("new_kpi", True)]
    assert any(c.name == "new_kpi" and c.group is Group.UNCLASSIFIED for c in effective_registry())
    assert "new_kpi" in query_builder.additive_measures()

    # The physical fact column now exists (the sync will populate its values).
    async with metrics_env.sessionmaker() as s:
        cols = await schema_reconcile._physical_columns(s, "fact_daily_performance")
    assert "new_kpi" in cols


async def test_fact_schema_sync_deactivates_promoted_column(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dynamic column later PROMOTED into the static registry (the apple_account case) is
    deactivated by the reconcile — leaving it active made the sync's COPY column list carry
    the name twice → 'DuplicateColumn … specified more than once' and a failed sync daily."""
    monkeypatch.setattr(integration_service, "_bq_key_present", lambda _s: True)
    async with metrics_env.sessionmaker() as s:
        await s.execute(
            insert(DynamicColumn).values(
                table_kind="fact",
                name="apple_account",  # now a STATIC registry column
                pg_type="TEXT",
                bq_type="STRING",
                active=True,
            )
        )
        await s.commit()

    actual = {c.name: c.bq_type for c in metric_registry.REGISTRY}  # incl. apple_account

    def fake_run(key_path: str, project: str, view: str) -> tuple[dict[str, str] | None, None]:
        return (actual, None)

    monkeypatch.setattr(integration_service, "_run_schema_diff", fake_run)

    body = (
        await metrics_env.client.post(
            "/api/v1/admin/integration/schema-sync", headers=_auth("admin")
        )
    ).json()
    assert body["ok"] is True
    assert "apple_account" in body["deactivated"]
    async with metrics_env.sessionmaker() as s:
        row = (
            await s.execute(
                select(DynamicColumn).where(
                    DynamicColumn.table_kind == "fact", DynamicColumn.name == "apple_account"
                )
            )
        ).scalar_one()
    assert row.active is False  # healed — the static column serves it from now on


def test_effective_registry_dedupes_promoted_dynamic() -> None:
    """Static registry wins over a dynamic column of the same name — never served twice."""
    from app.core.metric_registry import Col, set_dynamic_columns

    try:
        set_dynamic_columns([Col("apple_account", "STRING", "TEXT", Group.UNCLASSIFIED)])
        names = [c.name for c in effective_registry()]
        assert names.count("apple_account") == 1
        # And the surviving entry is the curated static one (dimension), not unclassified.
        col = next(c for c in effective_registry() if c.name == "apple_account")
        assert col.group is not Group.UNCLASSIFIED
    finally:
        set_dynamic_columns([])  # never leak state into other tests


async def test_fact_schema_sync_flags_removed_column(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(integration_service, "_bq_key_present", lambda _s: True)
    # Pre-existing dynamic column that has since vanished from BigQuery.
    async with metrics_env.sessionmaker() as s:
        await s.execute(
            insert(DynamicColumn).values(
                table_kind="fact", name="old_metric", pg_type="BIGINT", bq_type="INT64", active=True
            )
        )
        await s.commit()

    actual = {c.name: c.bq_type for c in metric_registry.REGISTRY}  # old_metric NOT present

    def fake_run(key_path: str, project: str, view: str) -> tuple[dict[str, str] | None, None]:
        return (actual, None)

    monkeypatch.setattr(integration_service, "_run_schema_diff", fake_run)

    body = (
        await metrics_env.client.post(
            "/api/v1/admin/integration/schema-sync", headers=_auth("admin")
        )
    ).json()
    assert body["deactivated"] == ["old_metric"]
    # Flagged, NOT dropped — the row and its data are kept.
    async with metrics_env.sessionmaker() as s:
        row = (
            await s.execute(select(DynamicColumn).where(DynamicColumn.name == "old_metric"))
        ).scalar_one()
    assert row.active is False

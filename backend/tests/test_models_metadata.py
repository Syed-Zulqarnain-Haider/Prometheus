"""Verify the ORM metadata faithfully reflects ``sql/postgres/001_init.sql``."""

from app.models import Base

EXPECTED_TABLES = {
    "dim_app",
    "users",
    "roles",
    "user_roles",
    "role_metric_permissions",
    "role_capabilities",
    "user_scopes",
    "saved_views",
    "saved_reports",
    "report_shares",
    "audit_log",
    "sync_runs",
}


def test_all_001_tables_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_fact_table_is_not_modeled():
    # The sync-owned fact table must NOT be managed by the ORM/Alembic.
    assert "fact_daily_performance" not in Base.metadata.tables


def test_composite_primary_keys():
    tables = Base.metadata.tables
    assert [c.name for c in tables["user_roles"].primary_key.columns] == [
        "user_id",
        "role_id",
    ]
    assert [c.name for c in tables["role_metric_permissions"].primary_key.columns] == [
        "role_id",
        "metric_group",
    ]
    assert [c.name for c in tables["role_capabilities"].primary_key.columns] == [
        "role_id",
        "capability",
    ]


def test_partial_index_on_report_shares():
    idx = next(
        i for i in Base.metadata.tables["report_shares"].indexes if i.name == "idx_shares_pending"
    )
    assert idx.dialect_options["postgresql"]["where"] is not None


def test_check_constraints_present():
    # The naming convention expands check names to ck_<table>_<name>.
    scopes = Base.metadata.tables["user_scopes"]
    names = {c.name for c in scopes.constraints}
    assert "ck_user_scopes_scope_type_valid" in names
    assert "ck_user_scopes_scope_value_required" in names

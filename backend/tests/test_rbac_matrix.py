"""The RBAC wall — exhaustive matrix tests for the RBAC core.

Covers, for every role:
  * exactly which metric-group columns serialize in the generated response model
    (and that forbidden groups never appear);
  * that those role→group / role→capability mappings match the DB seed;
  * the capability dependency allow/deny matrix (role × capability);
and that the scope resolver compiles to the exact expected SQL.
"""

import uuid

import pytest
from app.api.deps import require_capability
from app.core.metric_registry import REGISTRY, Group, columns_for_groups
from app.models import Role, RoleCapability, RoleMetricPermission
from app.schemas.auth import ScopeOut, UserContext
from app.services.response_models import build_response_model, groups_from_names
from app.services.scopes import build_scope_filter
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

# ── Authoritative expectations (mirror CLAUDE.md / 001_init.sql seed) ────────
ALL_METRIC_GROUPS = {
    Group.STORE_INSTALLS,
    Group.UA_SPEND,
    Group.AD_REVENUE,
    Group.IAP_REVENUE,
    Group.ATTRIBUTION,
    Group.PROFITABILITY,
}
FULL = set(ALL_METRIC_GROUPS)
MARKETING_FINANCE = {
    Group.STORE_INSTALLS,
    Group.UA_SPEND,
    Group.AD_REVENUE,
    Group.IAP_REVENUE,  # marketing includes iap_revenue (owner decision)
    Group.PROFITABILITY,
}

ROLE_METRIC_GROUPS: dict[str, set[Group]] = {
    "admin": FULL,
    "executive": FULL,
    "pod_owner": FULL,
    "marketing": MARKETING_FINANCE,
    "finance": MARKETING_FINANCE,
    "viewer": {Group.STORE_INSTALLS},
}

ALL_CAPABILITIES = {"export", "share_report", "admin_panel"}
ROLE_CAPABILITIES: dict[str, set[str]] = {
    "admin": {"export", "share_report", "admin_panel"},
    "executive": {"export", "share_report"},
    "pod_owner": {"export", "share_report"},
    "marketing": {"export", "share_report"},
    "finance": {"export", "share_report"},
    "viewer": set(),
}

DIMENSION_COLUMNS = {c.name for c in REGISTRY if c.group == Group.DIMENSION}


def _make_context(*, capabilities: set[str]) -> UserContext:
    return UserContext(
        user_id=uuid.uuid4(),
        firebase_uid="uid",
        email="u@terafort.org",
        display_name=None,
        is_active=True,
        roles=["test"],
        metric_groups=[],
        capabilities=sorted(capabilities),
        scopes=[],
    )


# ── (b) Per-role response-model column serialization ─────────────────────────
@pytest.mark.parametrize("role", list(ROLE_METRIC_GROUPS))
def test_response_model_serializes_exactly_permitted_columns(role: str) -> None:
    groups = ROLE_METRIC_GROUPS[role]
    model = build_response_model(frozenset(groups), name=f"Row_{role}")
    fields = set(model.model_fields)

    permitted_metric_cols = set(columns_for_groups(groups))
    forbidden_metric_cols = set(columns_for_groups(ALL_METRIC_GROUPS - groups))

    # Every permitted metric column is present...
    assert permitted_metric_cols <= fields
    # ...no forbidden metric column leaks...
    assert fields.isdisjoint(forbidden_metric_cols)
    # ...dimensions always serialize, the system column never does.
    assert fields >= DIMENSION_COLUMNS
    assert "_built_at" not in fields
    # The model is exactly dimensions + permitted metrics, nothing else.
    assert fields == DIMENSION_COLUMNS | permitted_metric_cols


def test_groups_from_names_roundtrip() -> None:
    assert groups_from_names(frozenset({"store_installs", "ua_spend"})) == frozenset(
        {Group.STORE_INSTALLS, Group.UA_SPEND}
    )


# ── Role→group / role→capability expectations match the DB seed ──────────────
async def test_role_metric_groups_match_seed(db_session) -> None:
    rows = (
        await db_session.execute(
            select(Role.name, RoleMetricPermission.metric_group).join(
                RoleMetricPermission, RoleMetricPermission.role_id == Role.id
            )
        )
    ).all()
    seeded: dict[str, set[str]] = {}
    for role_name, group in rows:
        seeded.setdefault(role_name, set()).add(group)

    expected = {role: {g.value for g in groups} for role, groups in ROLE_METRIC_GROUPS.items()}
    assert seeded == expected


async def test_role_capabilities_match_seed(db_session) -> None:
    rows = (
        await db_session.execute(
            select(Role.name, RoleCapability.capability).join(
                RoleCapability, RoleCapability.role_id == Role.id
            )
        )
    ).all()
    seeded: dict[str, set[str]] = {}
    for role_name, capability in rows:
        seeded.setdefault(role_name, set()).add(capability)
    # Roles with zero capabilities (viewer) won't appear in the join.
    expected = {role: caps for role, caps in ROLE_CAPABILITIES.items() if caps}
    assert seeded == expected


# ── (c) Capability dependency allow/deny matrix ──────────────────────────────
@pytest.mark.parametrize("role", list(ROLE_CAPABILITIES))
async def test_capability_dependency_matrix(role: str) -> None:
    caps = ROLE_CAPABILITIES[role]
    context = _make_context(capabilities=caps)
    for capability in ALL_CAPABILITIES:
        dependency = require_capability(capability)
        if capability in caps:
            assert await dependency(context) is context
        else:
            with pytest.raises(HTTPException) as exc_info:
                await dependency(context)
            assert exc_info.value.status_code == 403


# ── (a) Scope resolver compiles to the exact expected SQL ────────────────────
def _sql(scopes: list[ScopeOut]) -> str:
    expr = build_scope_filter(scopes)
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_scope_all_short_circuits_to_true() -> None:
    assert _sql([ScopeOut(scope_type="all", scope_value=None)]) == "true"


def test_scope_all_wins_even_with_other_rows() -> None:
    assert (
        _sql(
            [
                ScopeOut(scope_type="all", scope_value=None),
                ScopeOut(scope_type="pod", scope_value="P1"),
            ]
        )
        == "true"
    )


def test_no_scopes_fails_closed() -> None:
    assert _sql([]) == "false"


def test_single_pod_scope() -> None:
    assert (
        _sql([ScopeOut(scope_type="pod", scope_value="POD_A")])
        == "fact_daily_performance.pod IN ('POD_A')"
    )


def test_multiple_same_type_scopes_are_sorted_in_clause() -> None:
    assert (
        _sql(
            [
                ScopeOut(scope_type="pod", scope_value="POD_B"),
                ScopeOut(scope_type="pod", scope_value="POD_A"),
            ]
        )
        == "fact_daily_performance.pod IN ('POD_A', 'POD_B')"
    )


def test_app_scope_uses_canonical_key() -> None:
    assert (
        _sql(
            [
                ScopeOut(scope_type="app", scope_value="k2"),
                ScopeOut(scope_type="app", scope_value="k1"),
            ]
        )
        == "fact_daily_performance.canonical_key IN ('k1', 'k2')"
    )


def test_mixed_scopes_or_in_fixed_order() -> None:
    assert _sql(
        [
            ScopeOut(scope_type="app", scope_value="appK"),
            ScopeOut(scope_type="publisher", scope_value="Pub1"),
            ScopeOut(scope_type="pod", scope_value="P1"),
            ScopeOut(scope_type="hou", scope_value="H1"),
        ]
    ) == (
        "fact_daily_performance.hou IN ('H1') "
        "OR fact_daily_performance.pod IN ('P1') "
        "OR fact_daily_performance.publisher IN ('Pub1') "
        "OR fact_daily_performance.canonical_key IN ('appK')"
    )

"""Row-level scope resolver.

Translates a user's ``user_scopes`` rows into a SQLAlchemy boolean filter over
``fact_daily_performance`` (CLAUDE.md RBAC):

  * an ``all`` scope short-circuits to "no restriction" (``true()``);
  * otherwise the effective access is the UNION of the user's rows, expressed as
    an OR of ``IN`` predicates: hou / pod / publisher, plus canonical_key for app
    scopes;
  * a user with NO scopes can see NO rows (``false()``) — fail closed.

This filter is injected FIRST in every data query; client filters may only
narrow it further, never widen it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, false, or_, true

from app.core.fact_table import FACT_TABLE
from app.schemas.auth import ScopeOut

# scope_type -> fact column used to enforce it. Order is fixed for deterministic SQL.
SCOPE_TYPE_TO_COLUMN: dict[str, str] = {
    "hou": "hou",
    "pod": "pod",
    "publisher": "publisher",
    "app": "canonical_key",
}
_SCOPE_ORDER = ("hou", "pod", "publisher", "app")


def _fact_scope_columns() -> dict[str, Any]:
    return {st: FACT_TABLE.c[col] for st, col in SCOPE_TYPE_TO_COLUMN.items()}


def build_scope_filter(
    scopes: Sequence[ScopeOut],
    *,
    columns: Mapping[str, Any] | None = None,
) -> ColumnElement[bool]:
    """Build the WHERE predicate enforcing a user's row scopes.

    ``columns`` maps each scope_type (hou/pod/publisher/app) to the column to
    enforce it against. Defaults to ``fact_daily_performance`` columns; pass
    ``dim_app`` columns to scope the apps endpoints.
    """
    scope_columns = columns if columns is not None else _fact_scope_columns()
    scope_types = {s.scope_type for s in scopes}

    # 'all' grants everything — no row restriction.
    if "all" in scope_types:
        return true()

    # No scopes at all → fail closed (no rows).
    if not scopes:
        return false()

    conditions: list[ColumnElement[bool]] = []
    for scope_type in _SCOPE_ORDER:
        values = sorted(
            {
                s.scope_value
                for s in scopes
                if s.scope_type == scope_type and s.scope_value is not None
            }
        )
        if values:
            conditions.append(scope_columns[scope_type].in_(values))

    if not conditions:
        return false()
    if len(conditions) == 1:
        return conditions[0]
    return or_(*conditions)

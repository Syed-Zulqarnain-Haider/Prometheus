"""Per-role Pydantic response-model generator.

Builds a Pydantic model whose fields are EXACTLY the columns the caller's metric
groups permit (plus the always-visible dimension columns used to label rows).
Forbidden metric columns are never declared, so they can never be serialized —
RBAC column filtering is enforced by the type system, not by hand-maintained
lists. Driven entirely by the metric registry (single source of truth).
"""

from __future__ import annotations

from datetime import date, datetime
from functools import cache
from typing import Any

from pydantic import BaseModel, create_model

from app.core.metric_registry import REGISTRY, Col, Group

# Dimensions always serialize (they label rows); SYSTEM (_built_at) never does.
_ALWAYS_INCLUDED: frozenset[Group] = frozenset({Group.DIMENSION})
_NEVER_INCLUDED: frozenset[Group] = frozenset({Group.SYSTEM})


def _python_type(pg_type: str) -> type:
    pg = pg_type.strip().upper()
    if pg == "DATE":
        return date
    if pg == "TIMESTAMPTZ":
        return datetime
    if pg == "TEXT":
        return str
    if pg == "BIGINT":
        return int
    if pg == "BOOLEAN":
        return bool
    if pg == "DOUBLE PRECISION" or pg.startswith("NUMERIC"):
        return float
    raise ValueError(f"Unmapped registry pg_type: {pg_type!r}")


def permitted_columns(groups: frozenset[Group]) -> list[Col]:
    """Registry columns visible to a caller holding ``groups`` (+ dimensions)."""
    allowed = (set(groups) | _ALWAYS_INCLUDED) - _NEVER_INCLUDED
    return [col for col in REGISTRY if col.group in allowed]


@cache
def build_response_model(groups: frozenset[Group], name: str = "PerformanceRow") -> type[BaseModel]:
    """Build (and cache) a Pydantic model for the given permitted metric groups.

    All fields are optional (fact rows can contain NULLs / source-lag zeros).
    """
    fields: dict[str, Any] = {
        col.name: (_python_type(col.pg_type) | None, None) for col in permitted_columns(groups)
    }
    return create_model(name, **fields)


def groups_from_names(names: frozenset[str]) -> frozenset[Group]:
    """Convert metric-group string names (e.g. from the DB) to Group members."""
    return frozenset(Group(name) for name in names)

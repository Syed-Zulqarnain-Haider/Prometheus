"""SQLAlchemy Core definition of the sync-owned ``fact_daily_performance`` table.

Generated from the metric registry. This lives in its OWN MetaData (not the ORM
``Base``), so Alembic never manages it — the sync job owns its lifecycle. The
query builder (Step 3) and the scope resolver build SQL against this object.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Computed,
    Date,
    DateTime,
    Float,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    types,
)

from app.core.metric_registry import REGISTRY

_NUMERIC_RE = re.compile(r"NUMERIC\((\d+),\s*(\d+)\)", re.IGNORECASE)


def _sa_type(pg_type: str) -> types.TypeEngine[Any]:
    """Map a registry Postgres type string to a SQLAlchemy type."""
    pg = pg_type.strip().upper()
    if pg == "DATE":
        return Date()
    if pg == "TEXT":
        return Text()
    if pg == "BIGINT":
        return BigInteger()
    if pg == "BOOLEAN":
        return Boolean()
    if pg == "DOUBLE PRECISION":
        return Float()
    if pg == "TIMESTAMPTZ":
        return DateTime(timezone=True)
    match = _NUMERIC_RE.fullmatch(pg)
    if match:
        return Numeric(int(match.group(1)), int(match.group(2)))
    raise ValueError(f"Unmapped registry pg_type: {pg_type!r}")


fact_metadata = MetaData()

FACT_TABLE = Table(
    "fact_daily_performance",
    fact_metadata,
    *[Column(col.name, _sa_type(col.pg_type)) for col in REGISTRY],
    # Generated natural-key component + primary key — mirrors the sync's generate_fact_ddl
    # and sql/postgres/002_fact_table.sql, so create_all (single-VM bootstrap + tests)
    # produces the SAME schema the sync UPSERTs into: ON CONFLICT (date, platform, app_key).
    Column(
        "app_key",
        Text(),
        Computed(
            "COALESCE(canonical_key, android_package, CAST(apple_id AS TEXT), 'unknown')",
            persisted=True,
        ),
    ),
    PrimaryKeyConstraint("date", "platform", "app_key", name="fact_daily_performance_pkey"),
)

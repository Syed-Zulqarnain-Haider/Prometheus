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
    Date,
    DateTime,
    Float,
    MetaData,
    Numeric,
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
    # Generated column used in the primary key (see 002_fact_table.sql).
    Column("app_key", Text()),
)

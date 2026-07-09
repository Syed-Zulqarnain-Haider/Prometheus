"""``app_master`` table — the Postgres serving copy of BigQuery
``terafort.cross_platform.app_master_v2``.

Built as a Core ``Table`` from the single-source column registry (so schema, sync and
write-back can never drift), attached to ``Base.metadata`` so Alembic manages its lifecycle.
Data is refreshed from BigQuery by the app-master sync; admin edits write back to BigQuery
and update this copy.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Table, Text, types

from app.core.app_master_columns import PRIMARY_KEY, REGISTRY
from app.models.base import Base

_SCALAR_TYPES: dict[str, type[types.TypeEngine[Any]]] = {
    "text": Text,
    "bigint": BigInteger,
    "boolean": Boolean,
    "double": Float,
}


def _column(name: str, pg_type: str) -> Column[Any]:
    sa_type: types.TypeEngine[Any] = (
        DateTime(timezone=True) if pg_type == "timestamptz" else _SCALAR_TYPES[pg_type]()
    )
    return Column(name, sa_type, primary_key=(name == PRIMARY_KEY))


APP_MASTER_TABLE = Table(
    "app_master",
    Base.metadata,
    *[_column(c.name, c.pg_type) for c in REGISTRY],
)

"""``dynamic_columns`` — columns discovered in BigQuery that are not in the static
column registries (``metric_registry.py`` for the fact table, ``app_master_columns.py``
for App Master).

The admin "Match Database & BigQuery Schema" button reconciles the Postgres serving
schema to the live BigQuery schema. Any BigQuery column not covered by the static
registry is recorded here and added to Postgres (additively — never a destructive drop).

Security note (fact table): a dynamic fact column has NO curated RBAC metric group, so it
is treated as ``unclassified`` and is served ONLY to admins (who can already see every
metric group). Non-admin roles never see an unclassified column — see
``metric_registry.effective_registry`` / ``response_models.permitted_columns``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# table_kind values.
FACT = "fact"
APP_MASTER = "app_master"


class DynamicColumn(Base):
    """A BigQuery-discovered column added to a Postgres serving table by schema reconcile."""

    __tablename__ = "dynamic_columns"
    __table_args__ = (UniqueConstraint("table_kind", "name", name="uq_dynamic_columns_kind_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 'fact' | 'app_master' — which serving table this column belongs to.
    table_kind: Mapped[str] = mapped_column(Text, nullable=False)
    # Postgres/API column name (identifier-safe; reconcile refuses non-identifier names).
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Logical Postgres type string (TEXT / BIGINT / NUMERIC(18,4) / BOOLEAN / TIMESTAMPTZ / DATE).
    pg_type: Mapped[str] = mapped_column(Text, nullable=False)
    # BigQuery INFORMATION_SCHEMA data_type the column was mapped from.
    bq_type: Mapped[str] = mapped_column(Text, nullable=False)
    # False = the column has vanished from BigQuery; we KEEP the data and flag it (never drop).
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    added_by: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)

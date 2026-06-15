"""add tech_cost_usd to fact_daily_performance

Adds the ``tech_cost_usd`` fact column (registry-driven; feeds Gross Profit on the
Overview). The fact table is sync-owned and normally regenerated from the metric
registry on every sync's atomic swap, so this migration is an idempotent safety net
for an already-materialized table — it ADDs the column only if missing, and is a
no-op once the sync has rebuilt the table with the new registry. Must run with a
role that can ALTER the sync-owned table.

Revision ID: c61d82035094
Revises: c104cb1048bb
Create Date: 2026-06-15 06:32:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c61d82035094"
down_revision: str | None = "c104cb1048bb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "fact_daily_performance"


def upgrade() -> None:
    # IF NOT EXISTS: the daily sync may already have rebuilt the table from the
    # updated registry, in which case this is a no-op.
    op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS tech_cost_usd NUMERIC(18,4)")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS tech_cost_usd")

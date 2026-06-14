"""revenue targets

Revision ID: c104cb1048bb
Revises: 8e99211b3730
Create Date: 2026-06-14 09:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c104cb1048bb"
down_revision: str | None = "8e99211b3730"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revenue_targets",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("period_type", sa.Text(), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=True),
        sa.Column("target_usd", sa.Double(), nullable=False),
        sa.Column("set_by", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "period_type IN ('year','month')",
            name="revenue_targets_period_type_valid",
        ),
        sa.CheckConstraint(
            "(period_type = 'year' AND period_month IS NULL) "
            "OR (period_type = 'month' AND period_month BETWEEN 1 AND 12)",
            name="revenue_targets_month_valid",
        ),
        sa.CheckConstraint("target_usd >= 0", name="revenue_targets_nonneg"),
        sa.ForeignKeyConstraint(["set_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_revenue_targets_year",
        "revenue_targets",
        ["period_year"],
        unique=True,
        postgresql_where=sa.text("period_type = 'year'"),
    )
    op.create_index(
        "uq_revenue_targets_month",
        "revenue_targets",
        ["period_year", "period_month"],
        unique=True,
        postgresql_where=sa.text("period_type = 'month'"),
    )


def downgrade() -> None:
    op.drop_index("uq_revenue_targets_month", table_name="revenue_targets")
    op.drop_index("uq_revenue_targets_year", table_name="revenue_targets")
    op.drop_table("revenue_targets")

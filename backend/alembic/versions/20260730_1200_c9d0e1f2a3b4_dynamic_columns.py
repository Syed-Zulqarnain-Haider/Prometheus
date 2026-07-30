"""dynamic_columns — BigQuery-discovered columns added by admin schema reconcile

Records columns present in BigQuery but absent from the static registries. The admin
"Match Database & BigQuery Schema" button adds them to the Postgres serving tables
additively; ``active=false`` marks a column that has since vanished from BigQuery (kept,
never dropped). Fact-table dynamic columns are served to admins only (unclassified group).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-30 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dynamic_columns",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("table_kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("pg_type", sa.Text(), nullable=False),
        sa.Column("bq_type", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("added_by", UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "table_kind IN ('fact','app_master')", name="dynamic_columns_kind_valid"
        ),
        sa.UniqueConstraint("table_kind", "name", name="uq_dynamic_columns_kind_name"),
    )

    # Admins can already see every metric group, so the auto-discovered 'unclassified'
    # group leaks nothing to them; grant it so their response models include dynamic
    # fact columns. NO other role gets it — non-admins never see an unclassified column.
    # (The metric_group CHECK constraint is widened to allow the new value.)
    op.drop_constraint("metric_group_valid", "role_metric_permissions", type_="check")
    op.create_check_constraint(
        "metric_group_valid",
        "role_metric_permissions",
        "metric_group IN ('store_installs','ua_spend','ad_revenue','iap_revenue',"
        "'attribution','profitability','unclassified')",
    )
    op.execute(
        """
        INSERT INTO role_metric_permissions (role_id, metric_group)
        SELECT id, 'unclassified' FROM roles WHERE name = 'admin'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_metric_permissions WHERE metric_group = 'unclassified'")
    op.drop_constraint("metric_group_valid", "role_metric_permissions", type_="check")
    op.create_check_constraint(
        "metric_group_valid",
        "role_metric_permissions",
        "metric_group IN ('store_installs','ua_spend','ad_revenue','iap_revenue',"
        "'attribution','profitability')",
    )
    op.drop_table("dynamic_columns")

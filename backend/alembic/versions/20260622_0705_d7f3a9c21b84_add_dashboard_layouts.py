"""add dashboard_layouts (per-user Overview layout persistence)

Stores one saved react-grid-layout per (user, page) for the drag-and-drop
Overview. Private per user (PK includes user_id; FK cascades on user delete).

Revision ID: d7f3a9c21b84
Revises: c61d82035094
Create Date: 2026-06-22 07:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7f3a9c21b84"
down_revision: str | None = "c61d82035094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dashboard_layouts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page", sa.Text(), nullable=False),
        sa.Column("layout", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_dashboard_layouts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "page", name=op.f("pk_dashboard_layouts")),
    )
    op.create_index("idx_dashboard_layouts_user", "dashboard_layouts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_dashboard_layouts_user", table_name="dashboard_layouts")
    op.drop_table("dashboard_layouts")

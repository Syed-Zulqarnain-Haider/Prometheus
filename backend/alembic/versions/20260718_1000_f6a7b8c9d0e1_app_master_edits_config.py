"""app_master_edits (change history / undo / backup) + app_master_config (column order)

- ``app_master_edits``: one row per edit, storing before + after values of the changed
  columns — powers one-click Undo and is a per-change backup (who changed what, when).
- ``app_master_config``: single-row global UI config (admin-set column order shared by all).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-18 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_master_edits",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        # Editor link is nulled (not deleted) if the user is removed — history is preserved.
        sa.Column("editor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "edited_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("action", sa.Text(), nullable=False, server_default="edit"),
        sa.Column("before", JSONB(), nullable=True),  # prior values of the changed columns
        sa.Column("after", JSONB(), nullable=True),  # new values that were applied
        sa.Column("undone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(
            ["editor_user_id"], ["users.id"], name="fk_app_master_edits_editor", ondelete="SET NULL"
        ),
        sa.CheckConstraint("action IN ('edit','undo')", name="app_master_edits_action_valid"),
    )
    # "Most recent live edit for this app" — the query Undo runs.
    op.create_index(
        "ix_app_master_edits_key_id", "app_master_edits", ["canonical_key", sa.text("id DESC")]
    )

    op.create_table(
        "app_master_config",
        sa.Column("id", sa.Integer(), primary_key=True),  # always 1 (single global row)
        sa.Column("column_order", JSONB(), nullable=True),  # ordered list of column names
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name="fk_app_master_config_updated_by", ondelete="SET NULL"
        ),
        sa.CheckConstraint("id = 1", name="app_master_config_singleton"),
    )


def downgrade() -> None:
    op.drop_table("app_master_config")
    op.drop_index("ix_app_master_edits_key_id", table_name="app_master_edits")
    op.drop_table("app_master_edits")

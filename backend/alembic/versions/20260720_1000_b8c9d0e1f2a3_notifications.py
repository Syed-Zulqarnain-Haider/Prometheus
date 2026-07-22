"""notifications + notification_reads (RBAC-scoped in-app notifications)

A notification has an ``audience`` (all | admins | user:<uuid>) that governs who can see it;
``notification_reads`` tracks per-user read state. Admins see everything routed to admins;
other users see only 'all' and notifications addressed to them.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-20 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        # 'all' | 'admins' | 'user:<uuid>' — governs visibility.
        sa.Column("audience", sa.Text(), nullable=False, server_default="all"),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("detail", JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_notifications_actor", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_notifications_created", "notifications", [sa.text("created_at DESC")])
    op.create_index("ix_notifications_audience", "notifications", ["audience"])

    op.create_table(
        "notification_reads",
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], name="fk_notification_reads_notif",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_notification_reads_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("notification_id", "user_id", name="pk_notification_reads"),
    )


def downgrade() -> None:
    op.drop_table("notification_reads")
    op.drop_index("ix_notifications_audience", table_name="notifications")
    op.drop_index("ix_notifications_created", table_name="notifications")
    op.drop_table("notifications")

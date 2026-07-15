"""app_master: match live app_master_v2 (drop 2 phantom cols, add 3 real ones)

The live BigQuery ``app_master_v2`` schema differs from the initial registry (confirmed via
the App Master 'Check schema' diff): it has no ``3rd party OS`` / ``Transsion delightek``
columns, and it DOES have ``sana_mirror_package``, ``apero_active``, ``apero_last_revenue_at``.
This reconciles the Postgres serving copy so the sync/edit columns match the source.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-15 12:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("app_master", "third_party_os")
    op.drop_column("app_master", "transsion_delightek")
    op.add_column("app_master", sa.Column("sana_mirror_package", sa.Text(), nullable=True))
    op.add_column("app_master", sa.Column("apero_active", sa.Boolean(), nullable=True))
    op.add_column(
        "app_master", sa.Column("apero_last_revenue_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("app_master", "apero_last_revenue_at")
    op.drop_column("app_master", "apero_active")
    op.drop_column("app_master", "sana_mirror_package")
    op.add_column("app_master", sa.Column("transsion_delightek", sa.Boolean(), nullable=True))
    op.add_column("app_master", sa.Column("third_party_os", sa.Text(), nullable=True))

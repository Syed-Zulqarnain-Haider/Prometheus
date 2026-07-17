"""sync_runs.mode — distinguish full backfill vs rolling incremental syncs

Adds ``mode`` to ``sync_runs`` so the two sync kinds are recorded and the row-count
integrity check can compare like-for-like (a full backfill's row count must not be judged
against a 40-day incremental's). Existing rows are historical full pulls -> default 'full'.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-17 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_runs",
        sa.Column("mode", sa.Text(), nullable=False, server_default="full"),
    )
    op.create_check_constraint(
        "sync_runs_mode_valid", "sync_runs", "mode IN ('full','incremental')"
    )


def downgrade() -> None:
    op.drop_constraint("sync_runs_mode_valid", "sync_runs", type_="check")
    op.drop_column("sync_runs", "mode")

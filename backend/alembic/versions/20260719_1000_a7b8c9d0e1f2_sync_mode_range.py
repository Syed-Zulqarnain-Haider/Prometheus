"""allow 'range' in sync_runs.mode (custom date-range sync)

Widens the sync_runs.mode check constraint to include 'range' — an admin-chosen start..end
window that overwrites exactly those dates.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-19 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("sync_runs_mode_valid", "sync_runs", type_="check")
    op.create_check_constraint(
        "sync_runs_mode_valid", "sync_runs", "mode IN ('full','incremental','range')"
    )


def downgrade() -> None:
    op.drop_constraint("sync_runs_mode_valid", "sync_runs", type_="check")
    op.create_check_constraint("sync_runs_mode_valid", "sync_runs", "mode IN ('full','incremental')")

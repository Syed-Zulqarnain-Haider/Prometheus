"""report_shares.edit_status: request-to-edit for shared reports

A shared report is owner-editable only. A recipient who wants to edit must REQUEST edit
access (edit_status 'requested'); the owner or an admin grants it ('granted'). Only then can
the recipient edit. Default 'none'.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-30 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "report_shares",
        sa.Column("edit_status", sa.Text(), nullable=False, server_default="none"),
    )
    op.create_check_constraint(
        "report_shares_edit_status_valid",
        "report_shares",
        "edit_status IN ('none','requested','granted')",
    )


def downgrade() -> None:
    op.drop_constraint("report_shares_edit_status_valid", "report_shares", type_="check")
    op.drop_column("report_shares", "edit_status")

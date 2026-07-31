"""notifications v2: severity + clickable deep-link

Adds ``severity`` (info | warning | critical) so the bell can rank/colour notifications
(a sync crash is critical), and ``link`` — a relative dashboard path the notification opens
when clicked, so a user lands exactly where the change happened.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-30 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("severity", sa.Text(), nullable=False, server_default="info"),
    )
    op.add_column("notifications", sa.Column("link", sa.Text(), nullable=True))
    op.create_check_constraint(
        "notifications_severity_valid",
        "notifications",
        "severity IN ('info','warning','critical')",
    )


def downgrade() -> None:
    op.drop_constraint("notifications_severity_valid", "notifications", type_="check")
    op.drop_column("notifications", "link")
    op.drop_column("notifications", "severity")

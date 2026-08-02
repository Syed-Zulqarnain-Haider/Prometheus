"""users.sessions_revoked_at: 'sign out of all devices' support

Adds a nullable revoke timestamp; tokens issued before it are rejected live in
get_user_context. Idempotent.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-02 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS sessions_revoked_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS sessions_revoked_at")

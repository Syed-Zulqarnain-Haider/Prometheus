"""app_master: add net_revenue_share + console_owned_by (app_master_v2 additions)

Additively adds the two newer app_master_v2 columns to the serving ``app_master`` table,
matching app_master_columns.REGISTRY. net_revenue_share's BigQuery name has spaces
("Net Revenue Share"); the Postgres/serving name is the sanitized identifier. Idempotent.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-31 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (column, Postgres type) — mirrors app/core/app_master_columns.py.
_COLUMNS: list[tuple[str, str]] = [
    ("net_revenue_share", "DOUBLE PRECISION"),
    ("console_owned_by", "TEXT"),
]
_TABLE = "app_master"


def upgrade() -> None:
    for name, pg_type in _COLUMNS:
        op.execute(
            f'ALTER TABLE IF EXISTS {_TABLE} ADD COLUMN IF NOT EXISTS "{name}" {pg_type}'
        )


def downgrade() -> None:
    for name, _ in _COLUMNS:
        op.execute(f'ALTER TABLE IF EXISTS {_TABLE} DROP COLUMN IF EXISTS "{name}"')

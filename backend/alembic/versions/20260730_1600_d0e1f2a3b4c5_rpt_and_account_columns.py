"""fact_daily_performance: add rpt_* reported totals + console/account dimensions

Additively adds the finance-authoritative reported totals (rpt_gross_revenue_usd,
rpt_ua_cost_usd, rpt_tf_profit_usd, rpt_shares_fees_taxes_usd) and the store/console
account dimensions (google_play_account, apple_account, rpt_console) to the sync-owned
fact table, matching the metric registry. Idempotent and safe whether or not the fact
table exists yet (it is created by the sync on first run) — uses IF EXISTS / IF NOT EXISTS.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-30 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (column, Postgres type) — mirrors backend/app/core/metric_registry.py.
_COLUMNS: list[tuple[str, str]] = [
    ("google_play_account", "TEXT"),
    ("apple_account", "TEXT"),
    ("rpt_console", "TEXT"),
    ("rpt_gross_revenue_usd", "NUMERIC(18,4)"),
    ("rpt_ua_cost_usd", "NUMERIC(18,4)"),
    ("rpt_tf_profit_usd", "NUMERIC(18,4)"),
    ("rpt_shares_fees_taxes_usd", "NUMERIC(18,4)"),
]
_TABLE = "fact_daily_performance"


def upgrade() -> None:
    for name, pg_type in _COLUMNS:
        op.execute(
            f'ALTER TABLE IF EXISTS {_TABLE} ADD COLUMN IF NOT EXISTS "{name}" {pg_type}'
        )


def downgrade() -> None:
    for name, _ in _COLUMNS:
        op.execute(f'ALTER TABLE IF EXISTS {_TABLE} DROP COLUMN IF EXISTS "{name}"')

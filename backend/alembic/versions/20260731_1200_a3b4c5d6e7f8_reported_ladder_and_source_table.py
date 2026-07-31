"""fact_daily_performance: add the reported finance ladder (rpt_*); point sync at the source table

Additively adds the 20 finance-authoritative reported columns (rpt_first_time_installs …
rpt_total_deductions_usd) to the sync-owned fact table, matching the metric registry. Also
flips the `bq_view` operational setting from the (now-removed) contract view to the raw source
table `terafort.Final_Staging_tables.unified_daily_performance` — but ONLY if it still holds
the old default, so a custom-configured source is never clobbered. The sync now computes the
derived metrics itself (SOURCE_EXPR in metric_registry), so reading the table directly keeps
every KPI intact.

Idempotent and safe whether or not the fact table exists yet (it is created by the sync on
first run) — uses IF EXISTS / IF NOT EXISTS.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-31 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (column, Postgres type) — mirrors backend/app/core/metric_registry.py (the rpt_* ladder).
_COLUMNS: list[tuple[str, str]] = [
    ("rpt_first_time_installs", "BIGINT"),
    ("rpt_redownloads", "BIGINT"),
    ("rpt_total_installs", "BIGINT"),
    ("rpt_organic_installs", "BIGINT"),
    ("rpt_ad_revenue_usd", "NUMERIC(18,4)"),
    ("rpt_ad_revenue_after_share_usd", "NUMERIC(18,4)"),
    ("rpt_total_revenue_usd", "NUMERIC(18,4)"),
    ("rpt_net_revenue_usd", "NUMERIC(18,4)"),
    ("rpt_net_revenue_terafort_usd", "NUMERIC(18,4)"),
    ("rpt_gross_profit_usd", "NUMERIC(18,4)"),
    ("rpt_net_profit_usd", "NUMERIC(18,4)"),
    ("rpt_total_cost_usd", "NUMERIC(18,4)"),
    ("rpt_tax_fees_usd", "NUMERIC(18,4)"),
    ("rpt_withholding_tax_usd", "NUMERIC(18,4)"),
    ("rpt_store_fee_usd", "NUMERIC(18,4)"),
    ("rpt_partner_fees_usd", "NUMERIC(18,4)"),
    ("rpt_partner_share_app_usd", "NUMERIC(18,4)"),
    ("rpt_partner_share_transsion_usd", "NUMERIC(18,4)"),
    ("rpt_partner_share_usd", "NUMERIC(18,4)"),
    ("rpt_total_deductions_usd", "NUMERIC(18,4)"),
]
_TABLE = "fact_daily_performance"

_OLD_SOURCE = "terafort.api.daily_performance_v1"
_NEW_SOURCE = "terafort.Final_Staging_tables.unified_daily_performance"


def upgrade() -> None:
    for name, pg_type in _COLUMNS:
        op.execute(f'ALTER TABLE IF EXISTS {_TABLE} ADD COLUMN IF NOT EXISTS "{name}" {pg_type}')
    # Flip the source to the raw table, but only if it still holds the retired view default —
    # never overwrite a source an admin has deliberately set. value is JSONB (a quoted string).
    op.execute(
        "UPDATE app_settings "
        f"SET value = to_jsonb('{_NEW_SOURCE}'::text) "
        "WHERE key = 'bq_view' "
        f"AND value = to_jsonb('{_OLD_SOURCE}'::text)"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE app_settings "
        f"SET value = to_jsonb('{_OLD_SOURCE}'::text) "
        "WHERE key = 'bq_view' "
        f"AND value = to_jsonb('{_NEW_SOURCE}'::text)"
    )
    for name, _ in _COLUMNS:
        op.execute(f'ALTER TABLE IF EXISTS {_TABLE} DROP COLUMN IF EXISTS "{name}"')

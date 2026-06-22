"""add idx_fact_cover covering index for uncached metric queries

Adds a date-leading COVERING index on the sync-owned ``fact_daily_performance`` so
the hot, uncached Overview aggregates (summary / timeseries / breakdown / table) run
as INDEX-ONLY scans instead of scattered heap reads — ~16x fewer buffer reads under
production-like (uncorrelated) physical order, results unchanged.

This mirrors ``sync/metric_registry.generate_indexes`` (COVER_INDEX_COLUMNS) and
``sql/postgres/002_fact_table.sql`` so the index also survives the daily atomic swap;
this migration creates it on the ALREADY-materialized table now, without waiting for
the next sync. Indexes only — no column, query, RBAC, or data changes.

Built with CREATE INDEX CONCURRENTLY (no long lock on the live table) inside an
autocommit block, and IF NOT EXISTS so it is a no-op if the sync already created it.
Must run with a role that can create an index on the sync-owned table.

Revision ID: f4a1c9d2e7b3
Revises: e2b5c8f4a611
Create Date: 2026-06-22 12:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a1c9d2e7b3"
down_revision: str | None = "e2b5c8f4a611"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fact_cover
ON fact_daily_performance (date) INCLUDE (
  canonical_key, platform, apple_id, android_package, app_name, publisher,
  pod, pod_owner, hou, store_total_installs, store_organic_installs,
  total_paid_installs, total_revenue_usd, total_ua_spend_usd, total_ad_revenue_usd,
  total_iap_gross_usd, total_iap_net_usd, tech_cost_usd, profit_usd
)
"""

_DROP = "DROP INDEX CONCURRENTLY IF EXISTS idx_fact_cover"


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute(_CREATE)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(_DROP)

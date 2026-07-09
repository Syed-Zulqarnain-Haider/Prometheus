"""app_master serving table (Postgres copy of BigQuery app_master_v2)

Creates ``app_master`` — the admin-managed serving copy of
``terafort.cross_platform.app_master_v2``. Populated by the app-master sync (BQ -> PG);
admin edits write back to BigQuery and update this row. ``canonical_key`` is the primary key
(one row per app). Columns mirror ``app.core.app_master_columns`` (single source of truth);
two BigQuery columns with spaces map to ``third_party_os`` / ``transsion_delightek``.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-09 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_master",
        sa.Column("app_name", sa.Text(), nullable=True),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("ios_bundle_id", sa.Text(), nullable=True),
        sa.Column("android_package", sa.Text(), nullable=True),
        sa.Column("apple_account", sa.Text(), nullable=True),
        sa.Column("google_play_account", sa.Text(), nullable=True),
        sa.Column("facebook_app_id", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("developer", sa.Text(), nullable=True),
        sa.Column("pod", sa.BigInteger(), nullable=True),
        sa.Column("pod_owner", sa.Text(), nullable=True),
        sa.Column("hou", sa.Text(), nullable=True),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("app_type", sa.Text(), nullable=True),
        sa.Column("apple_id", sa.BigInteger(), nullable=True),
        sa.Column("google_play_status", sa.Text(), nullable=True),
        sa.Column("apple_status", sa.Text(), nullable=True),
        sa.Column("added_by", sa.Text(), nullable=True),
        sa.Column("first_added_to_master_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_in_source_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("facebook_active", sa.Boolean(), nullable=True),
        sa.Column("facebook_last_spend_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("google_ads_active", sa.Boolean(), nullable=True),
        sa.Column("google_ads_last_spend_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admob_active", sa.Boolean(), nullable=True),
        sa.Column("admob_last_revenue_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applovin_active", sa.Boolean(), nullable=True),
        sa.Column("applovin_last_revenue_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mintegral_pub_active", sa.Boolean(), nullable=True),
        sa.Column("mintegral_pub_last_revenue_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mintegral_adv_active", sa.Boolean(), nullable=True),
        sa.Column("mintegral_adv_last_spend_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("revenue_share_pct", sa.Float(), nullable=True),
        sa.Column("cost_share_pct", sa.Float(), nullable=True),
        sa.Column("partner_name", sa.Text(), nullable=True),
        sa.Column("partnership_terms", sa.Text(), nullable=True),
        sa.Column("in_apple_console", sa.Boolean(), nullable=True),
        sa.Column("in_gp_console", sa.Boolean(), nullable=True),
        sa.Column("ops_notes", sa.Text(), nullable=True),
        sa.Column("third_party_os", sa.Text(), nullable=True),
        sa.Column("transsion_delightek", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("canonical_key", name="pk_app_master"),
    )
    # Common filter/sort columns for the admin App Master page.
    op.create_index("ix_app_master_platform", "app_master", ["platform"])
    op.create_index("ix_app_master_hou", "app_master", ["hou"])
    op.create_index("ix_app_master_needs_review", "app_master", ["needs_review"])


def downgrade() -> None:
    op.drop_index("ix_app_master_needs_review", table_name="app_master")
    op.drop_index("ix_app_master_hou", table_name="app_master")
    op.drop_index("ix_app_master_platform", table_name="app_master")
    op.drop_table("app_master")

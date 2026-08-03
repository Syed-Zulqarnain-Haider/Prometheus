"""job_runs: cluster-wide once-per-day claim for daily background routines

Backs DB-based dedup of proactive alerts + digest so they fire exactly once across all
instances and across restarts (replacing the per-process in-memory guard). Idempotent.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-08-03 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS job_runs (
            job         TEXT NOT NULL,
            run_date    DATE NOT NULL,
            claimed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (job, run_date)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_runs")

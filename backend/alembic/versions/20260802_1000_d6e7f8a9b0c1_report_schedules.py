"""report_schedules: recurring email delivery of a saved report

Creates the ``report_schedules`` table backing scheduled report delivery. A schedule always
runs under its owner's RBAC and delivers only to that owner (see the model docstring), so it
is not a data-sharing path. Idempotent.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-02 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS report_schedules (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id     UUID NOT NULL REFERENCES saved_reports(id) ON DELETE CASCADE,
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cadence       TEXT NOT NULL,
            hour          INTEGER NOT NULL,
            day_of_week   INTEGER,
            day_of_month  INTEGER,
            fmt           TEXT NOT NULL DEFAULT 'xlsx',
            timezone      TEXT NOT NULL DEFAULT 'UTC',
            enabled       BOOLEAN NOT NULL DEFAULT true,
            last_run_on   DATE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT schedule_cadence_valid CHECK (cadence IN ('daily','weekly','monthly')),
            CONSTRAINT schedule_fmt_valid CHECK (fmt IN ('csv','xlsx')),
            CONSTRAINT schedule_hour_valid CHECK (hour BETWEEN 0 AND 23),
            CONSTRAINT schedule_dow_valid CHECK (day_of_week IS NULL OR day_of_week BETWEEN 0 AND 6),
            CONSTRAINT schedule_dom_valid
                CHECK (day_of_month IS NULL OR day_of_month BETWEEN 1 AND 28)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedules_enabled "
        "ON report_schedules (enabled) WHERE enabled"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_schedules_user ON report_schedules (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS report_schedules")

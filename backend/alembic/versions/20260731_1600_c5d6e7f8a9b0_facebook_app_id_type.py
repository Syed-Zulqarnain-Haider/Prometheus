"""app_master: facebook_app_id TEXT -> DOUBLE PRECISION (match BigQuery FLOAT64)

facebook_app_id is FLOAT64 in BigQuery but the registry had it as STRING/TEXT, which the
App Master schema check flagged as a type mismatch (blocking sync/edit). This aligns the
serving column type to the source. Values are numeric; empty strings coerce to NULL.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-31 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "app_master"
_COL = "facebook_app_id"


def upgrade() -> None:
    # TEXT -> DOUBLE PRECISION. A per-row cast of arbitrary TEXT would ABORT the whole
    # migration on any non-numeric value ("N/A", stray spaces/commas, legacy free text).
    # Guard with a numeric regex so anything non-numeric becomes NULL instead of failing the
    # deploy. btrim() tolerates surrounding whitespace; numeric strings cast cleanly.
    numeric_re = r"^[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?$"
    op.execute(
        f'ALTER TABLE IF EXISTS {_TABLE} '
        f'ALTER COLUMN "{_COL}" TYPE DOUBLE PRECISION '
        f"USING CASE WHEN btrim({_COL}::text) ~ '{numeric_re}' "
        f"THEN btrim({_COL}::text)::double precision ELSE NULL END"
    )


def downgrade() -> None:
    op.execute(
        f'ALTER TABLE IF EXISTS {_TABLE} '
        f'ALTER COLUMN "{_COL}" TYPE TEXT USING {_COL}::text'
    )

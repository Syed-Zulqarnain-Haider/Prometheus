"""user CRUD schema: access_expires_at + delete-safe FKs to users

Adds ``users.access_expires_at`` (NULL = permanent; existing users default to NULL, so
nobody's access changes on upgrade) and makes every FK that references ``users.id`` safe
for a hard user delete:

* audit_log.user_id, users.created_by, user_scopes.granted_by, app_settings.updated_by,
  revenue_targets.set_by  -> ON DELETE SET NULL  (records PRESERVED, actor unlinked — the
  append-only audit trail's content is untouched; the FK action, not an app UPDATE, nulls
  the link).
* report_shares.shared_by / shared_with -> ON DELETE CASCADE (a share to/from a deleted
  user is moot); report_shares.approved_by -> SET NULL.

(roles/scopes/dashboard_layouts/saved_views/saved_reports already cascade.)

The existing FK names vary (some hand-named, some auto), so each is discovered from
pg_constraint by (table, column) -> users rather than hardcoded, then recreated with the
canonical ``fk_<table>_<column>_users`` name + the delete action.

Revision ID: a1b2c3d4e5f6
Revises: f4a1c9d2e7b3
Create Date: 2026-06-24 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f4a1c9d2e7b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, ON DELETE action). report_shares.shared_by/with are NOT NULL -> CASCADE.
_USER_FKS: list[tuple[str, str, str]] = [
    ("audit_log", "user_id", "SET NULL"),
    ("users", "created_by", "SET NULL"),
    ("user_scopes", "granted_by", "SET NULL"),
    ("app_settings", "updated_by", "SET NULL"),
    ("revenue_targets", "set_by", "SET NULL"),
    ("report_shares", "shared_by", "CASCADE"),
    ("report_shares", "shared_with", "CASCADE"),
    ("report_shares", "approved_by", "SET NULL"),
]

_FIND_FK = sa.text(
    """
    SELECT conname FROM pg_constraint
    WHERE contype = 'f'
      AND conrelid = CAST(:tbl AS regclass)
      AND confrelid = CAST('users' AS regclass)
      AND conkey = ARRAY[(
          SELECT attnum FROM pg_attribute
          WHERE attrelid = CAST(:tbl AS regclass) AND attname = :col AND NOT attisdropped
      )]
    """
)


def _canonical(table: str, column: str) -> str:
    return f"fk_{table}_{column}_users"


def _recreate_user_fks(ondelete_by_key: dict[tuple[str, str], str | None]) -> None:
    conn = op.get_bind()
    for table, column, _ in _USER_FKS:
        current = conn.execute(_FIND_FK, {"tbl": table, "col": column}).scalar()
        if current is None:
            raise RuntimeError(f"no FK from {table}.{column} -> users found")
        op.drop_constraint(current, table, type_="foreignkey")
        op.create_foreign_key(
            _canonical(table, column),
            table,
            "users",
            [column],
            ["id"],
            ondelete=ondelete_by_key[(table, column)],
        )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    _recreate_user_fks({(t, c): action for t, c, action in _USER_FKS})


def downgrade() -> None:
    # Restore the original "no ON DELETE action" behavior, then drop the column.
    _recreate_user_fks({(t, c): None for t, c, _ in _USER_FKS})
    op.drop_column("users", "access_expires_at")

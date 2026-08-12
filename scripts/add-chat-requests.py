#!/usr/bin/env python3
"""Create the Alembic migration for the chat contact-request flow.

Adds two columns to ``conversations``:
  status        text NOT NULL DEFAULT 'accepted'  - new direct threads start 'pending';
                the default grandfathers every pre-existing thread in as accepted.
  requested_by  uuid NULL -> users.id (SET NULL)  - who sent the request.

The model/schema/service/route changes ship as file checkouts; this script only writes
the migration, detecting the current head instead of assuming it. Idempotent: if a
migration with this id already exists, it does nothing. Run `alembic upgrade head` after.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

VERSIONS = Path("backend/alembic/versions")
# Globally NEW id - a reused id silently no-ops the glob check below and the migration
# never runs (the announcements banner outage taught us this the hard way).
MIGRATION_ID = "f8b3d47a2c91"


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def detect_head() -> str:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if rev:
            revisions.add(rev.group(1))
        if down:
            parents.add(down.group(1))
    heads = revisions - parents
    if len(heads) != 1:
        die(f"expected exactly one migration head, found {len(heads)}: {sorted(heads)}")
    return heads.pop()


def main() -> None:
    if not VERSIONS.is_dir():
        die(f"{VERSIONS} not found - run from the repository root")
    existing = list(VERSIONS.glob(f"*{MIGRATION_ID}*"))
    if existing:
        print(f"skipped migration (already present: {existing[0].name})")
        return

    head = detect_head()
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
    path = VERSIONS / f"{stamp}_{MIGRATION_ID}_chat_requests.py"
    path.write_text(
        f'''"""Chat contact requests: conversations.status + requested_by.

Revision ID: {MIGRATION_ID}
Revises: {head}
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "{MIGRATION_ID}"
down_revision: str | None = "{head}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default 'accepted' grandfathers every existing thread; only NEW direct
    # threads are created 'pending' by application code.
    op.add_column(
        "conversations",
        sa.Column("status", sa.Text(), nullable=False, server_default="accepted"),
    )
    op.add_column(
        "conversations",
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_requested_by_users",
        "conversations",
        "users",
        ["requested_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_conversations_requested_by_users", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "requested_by")
    op.drop_column("conversations", "status")
'''
    )
    print(f"created {path.name} (revises {head}) - now run: alembic upgrade head")


if __name__ == "__main__":
    main()

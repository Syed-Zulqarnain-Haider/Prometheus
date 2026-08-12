#!/usr/bin/env python3
"""Create the Alembic migration for announcement call-to-action buttons.

Adds two nullable columns to ``announcements``:
  cta_label  text NULL - the pill button's text ("Learn how", "Start now")
  cta_url    text NULL - where it points; validated server-side to an in-app path
             ("/…") or an https:// URL, so a stored javascript: URL cannot become
             persistent XSS in a banner every user sees.

Both nullable with no default, so existing announcements are untouched and keep
rendering as plain ticker items. Idempotent - re-running does nothing. Run this AFTER
add-chat-requests.py in the same deploy (head detection chains them in order), then
`alembic upgrade head`.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

VERSIONS = Path("backend/alembic/versions")
# Globally NEW id - reusing one silently no-ops the glob check and the columns never land.
MIGRATION_ID = "c3a71e05d982"


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
    path = VERSIONS / f"{stamp}_{MIGRATION_ID}_announcement_cta.py"
    path.write_text(
        f'''"""Announcement call-to-action: cta_label + cta_url.

Revision ID: {MIGRATION_ID}
Revises: {head}
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "{MIGRATION_ID}"
down_revision: str | None = "{head}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("announcements", sa.Column("cta_label", sa.Text(), nullable=True))
    op.add_column("announcements", sa.Column("cta_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("announcements", "cta_url")
    op.drop_column("announcements", "cta_label")
'''
    )
    print(f"created {path.name} (revises {head}) - now run: alembic upgrade head")


if __name__ == "__main__":
    main()

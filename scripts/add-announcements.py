#!/usr/bin/env python3
"""Wire the announcements banner into the deployed backend.

The feature ships as whole new files (``models/messaging.py``, ``schemas/messaging.py``,
``services/messaging_service.py``, ``api/v1/messaging.py``). This script does the parts that
depend on files that have drifted from this tree:

  1. registers the models so Alembic and SQLAlchemy see them
  2. mounts the router in ``main.py`` - by COPYING the shape of an existing
     ``include_router`` line rather than assuming the prefix or arguments
  3. writes the migration, with ``down_revision`` detected from the revision graph

Everything is verified before anything is written, and re-running is a no-op.

Run from the repository root:  python3 scripts/add-chat.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

VERSIONS = Path("backend/alembic/versions")
MAIN = Path("backend/app/main.py")
MODELS_INIT = Path("backend/app/models/__init__.py")

MIGRATION_ID = "b7e2a9c4f1d8"
MIGRATION_NAME = "announcements"

MODEL_EDITS: list[tuple[str, str]] = [
    (
        "from app.models.access import AccessRequest",
        "from app.models.access import AccessRequest\n"
        "from app.models.announcements import Announcement",
    ),
    (
        '    "AccessRequest",',
        '    "AccessRequest",\n    "Announcement",',
    ),
]

MIGRATION_TEMPLATE = '''"""Platform announcements banner.

Revision ID: {rev}
Revises: {down}
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "{rev}"
down_revision = "{down}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False, server_default=sa.text("'info'")),
        sa.Column(
            "audience_roles",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{{}}'"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_announcements_active", "announcements", ["is_active", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_announcements_active", table_name="announcements")
    op.drop_table("announcements")
'''


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


def patch_main(text: str) -> str:
    """Add the import and the include_router call, matching this file's own conventions."""
    # Import: keep the block alphabetical, which is what ruff/isort enforces.
    import_anchor = "from app.api.v1 import layouts as layouts_routes\n"
    if text.count(import_anchor) != 1:
        die(f"{MAIN}: expected one '{import_anchor.strip()}', found {text.count(import_anchor)}")
    text = text.replace(
        import_anchor,
        import_anchor + "from app.api.v1 import announcements as announcements_routes\n",
        1,
    )

    # Registration: clone an existing single-line include_router call so the new route picks
    # up whatever prefix and arguments this app actually uses. Guessing that would be a
    # coin flip; copying it cannot be wrong.
    lines = text.splitlines(keepends=True)
    candidates = [
        i
        for i, line in enumerate(lines)
        if "include_router(" in line and "_routes.router" in line and line.rstrip().endswith(")")
    ]
    if not candidates:
        die(
            f"{MAIN}: found no single-line 'include_router(..._routes.router...)' to copy. "
            "Register the router by hand."
        )
    template = lines[candidates[-1]]
    new_line = re.sub(r"\b\w+_routes\.router", "announcements_routes.router", template, count=1)
    lines.insert(candidates[-1] + 1, new_line)
    return "".join(lines)


def main() -> None:
    for path in (MAIN, MODELS_INIT):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    main_text = MAIN.read_text()
    models_text = MODELS_INIT.read_text()

    main_done = "announcements_routes" in main_text
    models_done = "app.models.announcements" in models_text

    if not models_done:
        for anchor, _ in MODEL_EDITS:
            if models_text.count(anchor) != 1:
                die(
                    f"{MODELS_INIT}: anchor matched {models_text.count(anchor)} times, "
                    f"expected 1:\n    {anchor}"
                )

    existing = list(VERSIONS.glob(f"*{MIGRATION_ID}*.py"))
    head = None if existing else detect_head()

    # ── write ───────────────────────────────────────────────────────────────────
    if models_done:
        print(f"skipped  {MODELS_INIT} (already registered)")
    else:
        for anchor, replacement in MODEL_EDITS:
            models_text = models_text.replace(anchor, replacement, 1)
        MODELS_INIT.write_text(models_text)
        print(f"patched  {MODELS_INIT}")

    if main_done:
        print(f"skipped  {MAIN} (router already mounted)")
    else:
        MAIN.write_text(patch_main(main_text))
        print(f"patched  {MAIN}")

    if existing:
        print(f"skipped  migration (already present: {existing[0].name})")
    else:
        assert head is not None
        target = VERSIONS / f"20260812_0900_{MIGRATION_ID}_{MIGRATION_NAME}.py"
        target.write_text(MIGRATION_TEMPLATE.format(rev=MIGRATION_ID, down=head))
        print(f"created  {target}")
        print(f"         down_revision detected as {head}")


if __name__ == "__main__":
    main()

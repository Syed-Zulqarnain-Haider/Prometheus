#!/usr/bin/env python3
"""Wire up the profile + presence feature on the deployed backend.

The new code ships as whole files (``api/v1/profile.py``, ``services/people_service.py``,
``services/presence_service.py``, ``schemas/people.py``). This script does the three things
that cannot ship as whole files, because the targets have drifted from this tree:

  1. adds the profile columns and the ``user_avatars`` model to ``models/identity.py``
  2. registers the model, mounts the router on the existing ``/me`` router, and refreshes
     the presence heartbeat inside ``get_user_context``
  3. writes the Alembic migration with its ``down_revision`` DETECTED from the existing
     revision graph, rather than guessed

Two passes: every anchor is verified first, and nothing is written unless all of them match
exactly once. Re-running is a no-op.

Run from the repository root:  python3 scripts/add-profile-presence.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

VERSIONS = Path("backend/alembic/versions")

# ── (path, already-applied marker, [(anchor, replacement)]) ─────────────────────────
PATCHES: list[tuple[Path, str, list[tuple[str, str]]]] = [
    (
        Path("backend/app/models/identity.py"),
        "class UserAvatar",
        [
            (
                "from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, Text, text",
                "from sqlalchemy import (\n"
                "    Boolean,\n"
                "    DateTime,\n"
                "    ForeignKey,\n"
                "    LargeBinary,\n"
                "    SmallInteger,\n"
                "    Text,\n"
                "    text,\n"
                ")",
            ),
            (
                '    # SET NULL on delete: keep accounts created by a since-deleted admin '
                "(unlink the creator).\n"
                "    created_by: Mapped[uuid.UUID | None] = mapped_column(\n"
                '        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")\n'
                "    )",
                '    # SET NULL on delete: keep accounts created by a since-deleted admin '
                "(unlink the creator).\n"
                "    created_by: Mapped[uuid.UUID | None] = mapped_column(\n"
                '        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")\n'
                "    )\n"
                "\n"
                "    # ---- Profile (self-served; identity and access stay administered) ----\n"
                "    first_name: Mapped[str | None] = mapped_column(Text)\n"
                "    last_name: Mapped[str | None] = mapped_column(Text)\n"
                "    job_title: Mapped[str | None] = mapped_column(Text)\n"
                "    phone: Mapped[str | None] = mapped_column(Text)\n"
                "    timezone: Mapped[str | None] = mapped_column(Text)\n"
                "\n"
                "    # ---- Presence -------------------------------------------------------\n"
                "    # Durable half of presence. Live status comes from a self-expiring Redis\n"
                "    # heartbeat (presence_service); these columns answer 'when were they last\n"
                "    # here' once that heartbeat has lapsed. last_seen_at is written at most\n"
                "    # once every few minutes, never on every request.\n"
                "    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))\n"
                "    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))",
            ),
            (
                'class Role(Base):\n    __tablename__ = "roles"',
                "class UserAvatar(Base):\n"
                '    """A profile picture, stored in Postgres.\n'
                "\n"
                "    For a few dozen users the bytes are negligible, and keeping them here means\n"
                "    they survive a container rebuild with no volume to configure, and are covered\n"
                "    by the database backup that already runs before every deploy. The type is\n"
                "    recorded from the file's own magic bytes, never from the upload header.\n"
                '    """\n'
                "\n"
                '    __tablename__ = "user_avatars"\n'
                "\n"
                "    user_id: Mapped[uuid.UUID] = mapped_column(\n"
                "        UUID(as_uuid=True),\n"
                '        ForeignKey("users.id", ondelete="CASCADE"),\n'
                "        primary_key=True,\n"
                "    )\n"
                "    content_type: Mapped[str] = mapped_column(Text, nullable=False)\n"
                "    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)\n"
                "    updated_at: Mapped[datetime] = mapped_column(\n"
                '        DateTime(timezone=True), nullable=False, server_default=text("now()")\n'
                "    )\n"
                "\n"
                "\n"
                'class Role(Base):\n    __tablename__ = "roles"',
            ),
        ],
    ),
    (
        Path("backend/app/models/__init__.py"),
        "UserAvatar",
        [
            (
                "from app.models.identity import Role, User, UserRole",
                "from app.models.identity import Role, User, UserAvatar, UserRole",
            ),
            (
                '    "UserRole",',
                '    "UserRole",\n    "UserAvatar",',
            ),
        ],
    ),
    (
        Path("backend/app/api/deps.py"),
        "presence_service",
        [
            (
                "from app.schemas.auth import UserContext\nfrom app.services.auth import (",
                "from app.schemas.auth import UserContext\n"
                "from app.services import presence_service\n"
                "from app.services.auth import (",
            ),
            (
                "    firebase_claims = decoded.get(\"firebase\") or {}\n"
                '    request.state.two_factor = bool(firebase_claims.get("sign_in_second_factor"))\n'
                "    request.state.user_context = context\n"
                "    return context",
                "    firebase_claims = decoded.get(\"firebase\") or {}\n"
                '    request.state.two_factor = bool(firebase_claims.get("sign_in_second_factor"))\n'
                "    request.state.user_context = context\n"
                "\n"
                "    # Live presence. Refreshes a self-expiring Redis heartbeat on every request and\n"
                "    # persists last_seen_at at most once every few minutes. auth_time is when this\n"
                "    # token's holder actually authenticated, which is what 'last login' means.\n"
                "    auth_time = decoded.get(\"auth_time\")\n"
                "    await presence_service.touch(\n"
                "        cache,\n"
                "        db,\n"
                "        context.user_id,\n"
                "        login_at=(\n"
                "            datetime.fromtimestamp(float(auth_time), UTC) if auth_time else None\n"
                "        ),\n"
                "    )\n"
                "    return context",
            ),
        ],
    ),
    (
        Path("backend/app/api/v1/account.py"),
        "profile_router",
        [
            (
                "from app.api.deps import CurrentUser, DbSession, RedisClient",
                "from app.api.deps import CurrentUser, DbSession, RedisClient\n"
                "from app.api.v1.profile import router as profile_router",
            ),
            (
                'router = APIRouter(prefix="/me", tags=["account"], '
                "dependencies=[Depends(enforce_rate_limit)])",
                'router = APIRouter(prefix="/me", tags=["account"], '
                "dependencies=[Depends(enforce_rate_limit)])\n"
                "\n"
                "# Profile, avatar and the people directory hang off the same /me router so they\n"
                "# inherit its rate limiting and need no change to main.py.\n"
                "router.include_router(profile_router)",
            ),
        ],
    ),
]

MIGRATION_ID = "e9f1c2a3b4d5"
MIGRATION_NAME = "profiles_presence_avatars"
MIGRATION_TEMPLATE = '''"""Profile fields, presence timestamps and avatar storage.

Revision ID: {rev}
Revises: {down}
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Imported explicitly: `sa.dialects.postgresql` is a submodule and is only reachable off the
# `sa` namespace if something else already imported it. Relying on that is a coin flip.
from sqlalchemy.dialects import postgresql

revision = "{rev}"
down_revision = "{down}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All nullable: every column is optional profile detail, so this is additive and safe
    # to apply to a live table without a default backfill or a rewrite.
    op.add_column("users", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("job_title", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("timezone", sa.Text(), nullable=True))
    op.add_column(
        "users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "user_avatars",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_avatars")
    for column in (
        "last_seen_at",
        "last_login_at",
        "timezone",
        "phone",
        "job_title",
        "last_name",
        "first_name",
    ):
        op.drop_column("users", column)
'''


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def detect_head() -> str:
    """The revision no other migration builds on. Detected, never assumed."""
    if not VERSIONS.is_dir():
        die(f"{VERSIONS} not found - run from the repository root")
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
    # ── Pass 1: verify everything ───────────────────────────────────────────────
    todo: list[tuple[Path, str, list[tuple[str, str]]]] = []
    for path, marker, edits in PATCHES:
        if not path.exists():
            die(f"{path} not found")
        text = path.read_text()
        if marker in text:
            print(f"skipped  {path} (already patched)")
            continue
        for anchor, _ in edits:
            count = text.count(anchor)
            if count != 1:
                die(f"{path}: anchor matched {count} times, expected 1:\n    {anchor[:90]}...")
        todo.append((path, marker, edits))

    existing = list(VERSIONS.glob(f"*{MIGRATION_ID}*.py"))
    head = None if existing else detect_head()

    # ── Pass 2: write ───────────────────────────────────────────────────────────
    for path, _, edits in todo:
        text = path.read_text()
        for anchor, replacement in edits:
            text = text.replace(anchor, replacement, 1)
        path.write_text(text)
        print(f"patched  {path}")

    if existing:
        print(f"skipped  migration (already present: {existing[0].name})")
    else:
        assert head is not None
        target = VERSIONS / f"20260811_1200_{MIGRATION_ID}_{MIGRATION_NAME}.py"
        target.write_text(MIGRATION_TEMPLATE.format(rev=MIGRATION_ID, down=head))
        print(f"created  {target}")
        print(f"         down_revision detected as {head}")

    print("\nNext: apply the migration, then restart the backend:")
    print("  docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head")
    print("  docker compose -f docker-compose.prod.yml up -d --build backend frontend")


if __name__ == "__main__":
    main()

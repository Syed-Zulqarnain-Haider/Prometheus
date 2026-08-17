#!/usr/bin/env python3
"""Create the Alembic migration for TOTP two-factor authentication.

SCHEMA ONLY - deliberately inert. These tables exist but nothing reads or writes them
until the service and routes land, so applying this changes no behaviour and cannot
lock anyone out. That separation is the point: the risky half of an auth feature is the
enforcement path, not the storage, so they ship in different steps.

  user_totp
    user_id       uuid PK -> users.id (CASCADE)   one enrolment per person
    secret        text NOT NULL                    base32 TOTP secret
    confirmed_at  timestamptz NULL                 NULL = enrolment started but never
                                                   verified; treat as NOT enabled, so an
                                                   abandoned setup never blocks a login
    created_at    timestamptz NOT NULL default now()
    last_used_at  timestamptz NULL                 for replay defence + "last used" in UI

  user_recovery_codes
    id            uuid PK
    user_id       uuid -> users.id (CASCADE)
    code_hash     text NOT NULL                    HASHED, never the plaintext code
    used_at       timestamptz NULL                 single-use: set on redemption
    created_at    timestamptz NOT NULL default now()

Notes that matter later:
  * The secret is stored so the server can verify codes; it is NOT a password hash and
    cannot be one-way hashed. Protect it as a credential - it belongs in the database
    the api role reaches, never in a log or an API response after enrolment.
  * Recovery codes ARE hashed, because they are password-equivalent and single-use.
  * ``confirmed_at`` is what "2FA is on" means. Enrolment writes a row immediately so the
    QR can be shown, but until the user proves a code the row must not gate anything.

Idempotent. Run `alembic upgrade head` afterwards.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

VERSIONS = Path("backend/alembic/versions")
# Globally new id - a reused id silently no-ops the glob check and the tables never land.
MIGRATION_ID = "a4c81f60e35b"


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
        if rev:
            revisions.add(rev.group(1))
        for down in re.findall(r"^down_revision[^=]*=\s*(.+)$", text, re.M):
            parents.update(re.findall(r"[\"']([0-9a-f]{8,})[\"']", down))
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
    path = VERSIONS / f"{stamp}_{MIGRATION_ID}_totp_schema.py"
    path.write_text(
        f'''"""TOTP two-factor: user_totp + user_recovery_codes (schema only, inert).

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
    op.create_table(
        "user_totp",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("secret", sa.Text(), nullable=False),
        # NULL = enrolment started but never verified. Until this is set, 2FA is NOT on -
        # an abandoned setup must never be able to block a login.
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "user_recovery_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # HASHED, never the plaintext code - these are password-equivalent.
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    # Redemption looks up a user's UNUSED codes; one index serves that path.
    op.create_index(
        "ix_user_recovery_codes_user_unused",
        "user_recovery_codes",
        ["user_id"],
        postgresql_where=sa.text("used_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_user_recovery_codes_user_unused", table_name="user_recovery_codes")
    op.drop_table("user_recovery_codes")
    op.drop_table("user_totp")
'''
    )
    print(f"created {path.name} (revises {head})")
    print("\nSchema only - nothing reads these tables yet, so applying it changes no")
    print("behaviour. Next: the TOTP service, enrolment/verify routes, and the UI.")
    print("Run: docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head")


if __name__ == "__main__":
    main()

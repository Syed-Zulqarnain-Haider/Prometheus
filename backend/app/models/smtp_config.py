"""Editable SMTP configuration (``smtp_config``) — a single row, admin-managed.

Deliberately NOT part of ``app_settings``. That registry documents itself as having no
mechanism to store a credential, and constrains every value to a short format-validated
scalar so a secret can never be pasted into it. A mail password is exactly the thing it
refuses to hold, so it gets its own table with its own rules rather than a hole punched
in that one.

The password is stored ENCRYPTED (Fernet, key from the environment / Secret Manager) and
is never read back out through the API — only whether one is set. Every other field is
ordinary operational config and is stored as-is.

One row, enforced by a CHECK on a fixed primary key: "the SMTP settings" is a singleton,
and a table that can hold two of them invites the question of which one is live.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SmtpConfig(Base):
    __tablename__ = "smtp_config"
    __table_args__ = (CheckConstraint("id = 1", name="ck_smtp_config_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)

    host: Mapped[str | None] = mapped_column(Text, nullable=True)
    port: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("587"))
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Fernet ciphertext, never plaintext, and never returned by the API.
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

"""Access-request queue: authenticated-but-unprovisioned sign-ins awaiting approval."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AccessRequest(Base):
    """One row per Firebase identity that signed in without a provisioned account.

    A ``pending`` or ``rejected`` request grants ZERO access and NO role — only an admin
    APPROVE provisions a user. ``firebase_uid`` is UNIQUE so repeat sign-ins update the
    existing row (idempotent; no duplicates), and a rejected identity can re-request by
    signing in again (the row flips back to ``pending``).
    """

    __tablename__ = "access_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    firebase_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # The admin who approved/rejected (NULL while pending; unlinked if that admin is deleted).
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="status_valid"),
    )

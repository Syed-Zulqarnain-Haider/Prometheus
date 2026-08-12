"""Platform announcements: the admin-authored banner shown across the dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Announcement(Base):
    """One banner message.

    ``audience_roles`` holds role names (admin, executive, pod_owner, marketing, finance,
    viewer); an empty array means EVERYONE. Deactivation is a flag, not a delete, so the
    record of what was announced to whom survives - the banner is an administrative
    communication and keeps its trail like every other admin action.
    """

    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # info | success | warning | critical - drives the banner's colour.
    level: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'info'"))
    audience_roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

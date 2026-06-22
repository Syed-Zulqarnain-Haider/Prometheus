"""Per-user dashboard layouts (drag-and-drop Phase 2 persistence)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DashboardLayout(Base):
    """One saved layout per (user, page). Private to the owning user.

    ``layout`` stores the react-grid-layout ``Layouts`` object (breakpoint →
    item positions) for the draggable widgets below the fixed KPI header.
    """

    __tablename__ = "dashboard_layouts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    page: Mapped[str] = mapped_column(Text, primary_key=True)
    layout: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("idx_dashboard_layouts_user", "user_id"),)

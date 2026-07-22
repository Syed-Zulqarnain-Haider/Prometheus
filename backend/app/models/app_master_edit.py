"""ORM models for App Master change-history (undo/backup) and the global UI config."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppMasterEdit(Base):
    """One row per App Master edit — stores before + after values of the changed columns so
    an edit can be undone and every change is backed up (who/what/when)."""

    __tablename__ = "app_master_edits"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    canonical_key: Mapped[str] = mapped_column(Text, nullable=False)
    editor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'edit'"))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    undone: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        Index("ix_app_master_edits_key_id", "canonical_key", text("id DESC")),
        CheckConstraint("action IN ('edit','undo')", name="app_master_edits_action_valid"),
    )


class AppMasterConfig(Base):
    """Single-row (id=1) GLOBAL UI config for App Master — the admin-set column order that
    every user sees."""

    __tablename__ = "app_master_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    column_order: Mapped[list[str] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (CheckConstraint("id = 1", name="app_master_config_singleton"),)

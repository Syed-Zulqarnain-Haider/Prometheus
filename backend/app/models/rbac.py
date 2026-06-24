"""RBAC tables: ``role_metric_permissions``, ``role_capabilities``, ``user_scopes``."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RoleMetricPermission(Base):
    """Metric-group grants per role (admin-editable, no deploys)."""

    __tablename__ = "role_metric_permissions"

    role_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    metric_group: Mapped[str] = mapped_column(Text, primary_key=True)

    __table_args__ = (
        CheckConstraint(
            "metric_group IN ('store_installs','ua_spend','ad_revenue',"
            "'iap_revenue','attribution','profitability')",
            name="metric_group_valid",
        ),
    )


class RoleCapability(Base):
    """Capability flags per role (export / share_report / admin_panel)."""

    __tablename__ = "role_capabilities"

    role_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    capability: Mapped[str] = mapped_column(Text, primary_key=True)

    __table_args__ = (
        CheckConstraint(
            "capability IN ('export','share_report','admin_panel')",
            name="capability_valid",
        ),
    )


class UserScope(Base):
    """Row-level scope grants. Effective access = UNION of a user's rows."""

    __tablename__ = "user_scopes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_value: Mapped[str | None] = mapped_column(Text)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('all','hou','pod','publisher','app')",
            name="scope_type_valid",
        ),
        CheckConstraint(
            "(scope_type = 'all' AND scope_value IS NULL) "
            "OR (scope_type <> 'all' AND scope_value IS NOT NULL)",
            name="scope_value_required",
        ),
        UniqueConstraint(
            "user_id",
            "scope_type",
            "scope_value",
            name="user_scopes_user_id_scope_type_scope_value_key",
        ),
        Index("idx_scopes_user", "user_id"),
    )

"""Admin-set revenue targets (yearly + monthly) for the Overview progress donut."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RevenueTarget(Base):
    """A revenue goal for one period. ``period_type='year'`` rows leave
    ``period_month`` NULL; ``period_type='month'`` rows carry 1–12.

    Uniqueness is enforced by two partial indexes (one target per year, one per
    year+month), so a NULL month never collides with the monthly rows.
    """

    __tablename__ = "revenue_targets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    period_type: Mapped[str] = mapped_column(Text, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int | None] = mapped_column(Integer)
    target_usd: Mapped[float] = mapped_column(Double, nullable=False)
    set_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "period_type IN ('year','month')",
            name="revenue_targets_period_type_valid",
        ),
        CheckConstraint(
            "(period_type = 'year' AND period_month IS NULL) "
            "OR (period_type = 'month' AND period_month BETWEEN 1 AND 12)",
            name="revenue_targets_month_valid",
        ),
        CheckConstraint("target_usd >= 0", name="revenue_targets_nonneg"),
        Index(
            "uq_revenue_targets_year",
            "period_year",
            unique=True,
            postgresql_where=text("period_type = 'year'"),
        ),
        Index(
            "uq_revenue_targets_month",
            "period_year",
            "period_month",
            unique=True,
            postgresql_where=text("period_type = 'month'"),
        ),
    )

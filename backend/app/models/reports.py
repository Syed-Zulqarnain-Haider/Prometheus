"""Saved views, saved reports, and admin-approval report sharing."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SavedView(Base):
    __tablename__ = "saved_views"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("idx_views_user", "user_id"),)


class SavedReport(Base):
    __tablename__ = "saved_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    group_by: Mapped[str] = mapped_column(Text, nullable=False)
    sort: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "group_by IN ('app','pod','publisher','platform','hou','date')",
            name="group_by_valid",
        ),
        Index("idx_reports_user", "user_id"),
    )


class ReportShare(Base):
    __tablename__ = "report_shares"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("saved_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    # CASCADE: a share to/from a deleted user is moot — remove the share row.
    shared_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    shared_with: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    # Edit-access grant for this recipient: none | requested | granted. A shared report is
    # owner-editable only until an owner/admin grants edit here.
    edit_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'none'"))
    # SET NULL: keep an approved share if the approving admin is later deleted.
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','revoked')",
            name="status_valid",
        ),
        UniqueConstraint(
            "report_id", "shared_with", name="report_shares_report_id_shared_with_key"
        ),
        Index(
            "idx_shares_pending",
            "status",
            postgresql_where=text("status = 'pending'"),
        ),
    )


class ReportSchedule(Base):
    """A recurring email delivery of one saved report.

    RBAC-safe by construction: a schedule ALWAYS runs under its owner's own RBAC and delivers
    ONLY to that owner's email — it can never become a channel that hands another user data
    they couldn't see themselves. The report's date window is rolled forward at send time so
    each delivery carries fresh numbers of the same span.
    """

    __tablename__ = "report_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_reports.id", ondelete="CASCADE"), nullable=False
    )
    # Runs-as AND sole recipient. CASCADE: a deleted user's schedules are moot.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cadence: Mapped[str] = mapped_column(Text, nullable=False)  # daily | weekly | monthly
    hour: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-23 local
    day_of_week: Mapped[int | None] = mapped_column(Integer)  # 0=Mon..6=Sun (weekly)
    day_of_month: Mapped[int | None] = mapped_column(Integer)  # 1-28 (monthly)
    fmt: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'xlsx'"))
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'UTC'"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Local date of the last successful delivery — the per-day dedupe / claim key.
    last_run_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("cadence IN ('daily','weekly','monthly')", name="schedule_cadence_valid"),
        CheckConstraint("fmt IN ('csv','xlsx')", name="schedule_fmt_valid"),
        CheckConstraint("hour BETWEEN 0 AND 23", name="schedule_hour_valid"),
        CheckConstraint(
            "day_of_week IS NULL OR day_of_week BETWEEN 0 AND 6", name="schedule_dow_valid"
        ),
        CheckConstraint(
            "day_of_month IS NULL OR day_of_month BETWEEN 1 AND 28", name="schedule_dom_valid"
        ),
        Index("idx_schedules_enabled", "enabled", postgresql_where=text("enabled")),
        Index("idx_schedules_user", "user_id"),
    )

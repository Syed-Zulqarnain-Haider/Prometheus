"""Operational tables: append-only ``audit_log`` and ``sync_runs``."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Append-only audit trail. The api_service DB role has INSERT+SELECT only."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # SET NULL on delete: the append-only trail is PRESERVED (action/ip/detail/time intact)
    # when a user is removed — only the user link is nulled (a constraint action, not an
    # app-level UPDATE, so it does not weaken the no-UPDATE/DELETE rule on audit_log).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_audit_user_time", "user_id", text("created_at DESC")),
        Index("idx_audit_action_time", "action", text("created_at DESC")),
    )


class SyncRun(Base):
    """One row per daily sync execution."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))
    rows_loaded: Mapped[int | None] = mapped_column(BigInteger)
    rows_previous: Mapped[int | None] = mapped_column(BigInteger)
    bq_built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_detail: Mapped[str | None] = mapped_column(Text)
    # 'full' = backfill all history (UPSERT/accumulate); 'incremental' = re-pull the last
    # N days and OVERWRITE that window (delete + reload). The daily scheduler runs incremental.
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'full'"))

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','success','schema_mismatch','failed')",
            name="status_valid",
        ),
        CheckConstraint("mode IN ('full','incremental','range')", name="mode_valid"),
    )


class JobRun(Base):
    """Cluster-wide once-per-day claim for scheduled background routines.

    A row is the atomic proof that ``job`` already ran for ``run_date``. Instances race to
    ``INSERT ... ON CONFLICT DO NOTHING``; exactly one wins and does the work. This makes daily
    routines (proactive alerts, the digest) fire ONCE across all instances AND across restarts —
    replacing the per-process in-memory guard that duplicated emails per instance and per boot.
    """

    __tablename__ = "job_runs"

    job: Mapped[str] = mapped_column(Text, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

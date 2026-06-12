"""App dimension table (``dim_app``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DimApp(Base):
    """Latest mapping per app, refreshed by the sync job."""

    __tablename__ = "dim_app"

    canonical_key: Mapped[str] = mapped_column(Text, primary_key=True)
    app_name: Mapped[str | None] = mapped_column(Text)
    apple_id: Mapped[int | None] = mapped_column(BigInteger)
    android_package: Mapped[str | None] = mapped_column(Text)
    ios_bundle_id: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    pod: Mapped[str | None] = mapped_column(Text)
    pod_owner: Mapped[str | None] = mapped_column(Text)
    hou: Mapped[str | None] = mapped_column(Text)
    app_category: Mapped[str | None] = mapped_column(Text)
    ownership_type: Mapped[str | None] = mapped_column(Text)
    is_mapped: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

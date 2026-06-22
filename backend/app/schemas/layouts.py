"""Schemas for per-user dashboard layout persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DashboardLayoutSave(BaseModel):
    """Request body for saving a layout — the react-grid-layout ``Layouts`` object."""

    layout: dict[str, Any] = Field(
        ..., description="react-grid-layout Layouts (breakpoint → item positions)"
    )


class DashboardLayoutOut(BaseModel):
    """A user's saved layout for a page. ``layout`` is null when none is saved
    (the client then falls back to its default arrangement)."""

    page: str
    layout: dict[str, Any] | None = None
    updated_at: datetime | None = None

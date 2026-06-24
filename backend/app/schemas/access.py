"""Schemas for the access-request queue."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.admin import ScopeIn


class AccessRequestOut(BaseModel):
    id: uuid.UUID
    firebase_uid: str
    email: str
    display_name: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class AccessRequestStatus(BaseModel):
    """Returned to the requesting (unprovisioned) caller — never any role/scope."""

    status: str  # 'pending' after recording


class AccessRequestApprove(BaseModel):
    """Admin approval: provision the requester with this role + scope, optionally
    time-limited (absolute instant OR duration in days — backend converts)."""

    roles: list[str] = Field(default_factory=list)
    scopes: list[ScopeIn] = Field(default_factory=list)
    access_expires_at: datetime | None = None
    access_duration_days: int | None = Field(default=None, ge=1, le=3650)

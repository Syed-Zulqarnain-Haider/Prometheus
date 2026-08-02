"""Schemas for the self-service account security page."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DeviceActivity(BaseModel):
    """A recent sign-in / activity origin, grouped by device + network."""

    user_agent: str | None
    ip_address: str | None
    last_seen: datetime
    events: int


class SecurityStatus(BaseModel):
    two_factor: bool
    sessions_revoked_at: datetime | None
    devices: list[DeviceActivity]


class RevokeResult(BaseModel):
    revoked_at: datetime

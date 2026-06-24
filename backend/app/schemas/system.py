"""Schemas for the admin System tab: connection health, settings, sync trigger.

Connection statuses carry ONLY up/down/not_configured + latency — never a
connection string, host, or any credential.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ConnState = Literal["up", "down", "not_configured"]


class ConnectionStatus(BaseModel):
    name: str
    status: ConnState
    latency_ms: float | None = None
    detail: str | None = None  # human note only — never a connection string/credential


class SystemHealth(BaseModel):
    postgres: ConnectionStatus
    redis: ConnectionStatus
    bigquery: ConnectionStatus


class SettingOut(BaseModel):
    key: str
    type: str
    value: int | bool | str
    default: int | bool | str
    label: str
    description: str
    group: str = "general"
    minimum: int | None = None
    maximum: int | None = None
    updated_at: datetime | None = None


class SettingUpdate(BaseModel):
    # int/bool, or a SHORT format-validated string (HH:MM, IANA tz, GCP project, BQ
    # view) — the registry rejects anything else, so a secret blob can never be stored.
    value: int | bool | str


class SyncTriggerResult(BaseModel):
    triggered: bool
    configured: bool
    message: str


class ClientSettings(BaseModel):
    """Operational settings the frontend reads to react (non-secret)."""

    data_freshness_threshold_hours: int
    show_demo_widgets: bool

"""Schemas for in-app notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    created_at: datetime
    type: str
    title: str
    body: str | None
    severity: str = "info"  # info | warning | critical
    link: str | None = None  # relative path the notification opens when clicked
    resource: str | None
    detail: dict[str, Any] | None
    read: bool


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int

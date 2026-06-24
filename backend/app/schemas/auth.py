"""Auth-related response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ScopeOut(BaseModel):
    """A single row-level scope grant."""

    scope_type: str
    scope_value: str | None = None


class DirectoryEntry(BaseModel):
    """A minimal directory record used to pick report-share recipients."""

    user_id: uuid.UUID
    email: str
    display_name: str | None = None


class UserContext(BaseModel):
    """The resolved identity + RBAC for the authenticated caller.

    This object is cached in Redis (5-min TTL) and is the basis for all
    server-side authorization in later steps.
    """

    user_id: uuid.UUID
    firebase_uid: str
    email: str
    display_name: str | None = None
    is_active: bool
    # NULL = permanent. Enforced live on every request (see deps.get_user_context); a
    # default keeps any pre-existing cached context JSON deserializable.
    access_expires_at: datetime | None = None
    roles: list[str]
    metric_groups: list[str]
    capabilities: list[str]
    scopes: list[ScopeOut]

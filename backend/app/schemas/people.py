"""Schemas for the profile page and the people directory (with presence)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal["online", "away", "offline"]

# Bounds exist so a client cannot post a megabyte of text into a name column. They are
# generous enough for real names and titles in any script.
_MAX_NAME = 80
_MAX_TITLE = 120
_MAX_PHONE = 40


class ProfileOut(BaseModel):
    """The signed-in user's own profile."""

    user_id: uuid.UUID
    email: str
    first_name: str | None
    last_name: str | None
    display_name: str | None
    job_title: str | None
    phone: str | None
    timezone: str | None
    has_avatar: bool
    roles: list[str]
    last_login_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime


class ProfileUpdate(BaseModel):
    """Fields a user may change about themselves.

    Deliberately excludes email, roles, scopes and active status - identity and access are
    administered, never self-served, or any user could grant themselves anything.
    """

    first_name: str | None = Field(default=None, max_length=_MAX_NAME)
    last_name: str | None = Field(default=None, max_length=_MAX_NAME)
    job_title: str | None = Field(default=None, max_length=_MAX_TITLE)
    phone: str | None = Field(default=None, max_length=_MAX_PHONE)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("first_name", "last_name", "job_title", "phone", "timezone")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        """Treat "   " as clearing the field, so a cleared input does not store whitespace."""
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class PersonOut(BaseModel):
    """Another user, as seen in the directory, an avatar row, or a chat contact list."""

    user_id: uuid.UUID
    email: str
    display_name: str | None
    first_name: str | None
    last_name: str | None
    job_title: str | None
    roles: list[str]
    has_avatar: bool
    status: Status
    last_seen_at: datetime | None
    # Only populated for admins - when someone last authenticated is administrative detail,
    # not something every colleague needs to see.
    last_login_at: datetime | None = None


class PeopleList(BaseModel):
    people: list[PersonOut]
    online: int


class AvatarUploaded(BaseModel):
    has_avatar: bool
    bytes: int
    content_type: str

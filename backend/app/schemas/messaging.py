"""Schemas for person-to-person messaging."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.people import Status

# A generous ceiling that still stops a client posting a novel (or a payload designed to
# bloat the table). Long enough for a pasted stack trace or a table of numbers.
MAX_BODY = 8000


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_name: str | None
    body: str
    created_at: datetime
    edited_at: datetime | None
    deleted: bool
    # True when the caller wrote it, so the client can align the bubble without comparing ids.
    mine: bool


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """A message of pure whitespace is an accident, not a message."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Message cannot be empty")
        return trimmed


class ConversationPerson(BaseModel):
    """A participant, as shown in the conversation list and header."""

    user_id: uuid.UUID
    display_name: str | None
    email: str
    job_title: str | None
    has_avatar: bool
    status: Status
    last_seen_at: datetime | None


class ConversationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str | None
    # Everyone except the caller. For a direct thread this is the one person you are
    # talking to, which is what the list renders.
    participants: list[ConversationPerson]
    last_message_at: datetime | None
    last_message_preview: str | None
    last_message_mine: bool
    unread: int


class ConversationList(BaseModel):
    conversations: list[ConversationOut]
    unread_total: int


class DirectConversationCreate(BaseModel):
    """Open (or reopen) a direct thread with one person."""

    user_id: uuid.UUID


class MessagePage(BaseModel):
    messages: list[MessageOut]
    # Echoed back so a poller can ask for "anything after this" without tracking it itself.
    latest_at: datetime | None


class ReadResult(BaseModel):
    conversation_id: uuid.UUID
    last_read_at: datetime

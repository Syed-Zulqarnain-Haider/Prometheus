"""Schemas for person-to-person messaging."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

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
    # Delivery state for YOUR OWN messages, None for everyone else's. "delivered" means the
    # recipient's account has been active since the message was sent (this is a web app -
    # there is no device push to confirm against); "read" means their read marker passed it.
    # In a group, a state is only reached when EVERY other member has reached it.
    receipt: Literal["sent", "delivered", "read"] | None = None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_BODY)
    # user_ids this message @mentions. Validated server-side against the thread's
    # participants - a client cannot mention someone into a conversation they cannot see.
    mentions: list[uuid.UUID] = Field(default_factory=list, max_length=20)

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
    # Contact-request state: a direct thread is "pending" until the requested person
    # accepts; groups are always "accepted". requested_by_me tells the client which side
    # of a pending request the caller is on (sent vs received).
    status: Literal["pending", "accepted"] = "accepted"
    requested_by_me: bool = False


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


class AdminConversationOut(ConversationOut):
    """Oversight view: all participants (caller included) plus the thread's size."""

    message_count: int


class AdminConversationList(BaseModel):
    conversations: list[AdminConversationOut]


class GroupCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    member_ids: list[uuid.UUID] = Field(min_length=1, max_length=49)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Group name cannot be empty")
        return trimmed


class InviteCode(BaseModel):
    code: str
    expires_in_seconds: int


class JoinByCode(BaseModel):
    code: str = Field(min_length=4, max_length=32)

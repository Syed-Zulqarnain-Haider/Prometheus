"""Person-to-person messaging: conversations, participants and messages.

Distinct from ``chat_service`` / ``chat.py``, which is the AI data assistant. This is people
talking to people; the two share nothing but the word "chat".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Conversation(Base):
    """A thread. Either a direct pair or a named group."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # "direct" | "group"
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'direct'"))
    title: Mapped[str | None] = mapped_column(Text)

    # For a direct thread: the two participant ids, sorted and joined. Unique, so opening a
    # DM with the same person twice reuses the thread instead of quietly creating a second
    # one that splits the history. NULL for groups, and NULLs do not collide in a unique
    # index, so any number of groups coexist.
    direct_key: Mapped[str | None] = mapped_column(Text, unique=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # Contact-request flow (owner decision): a NEW direct thread starts "pending" and no
    # one can message in it until the requested person accepts. Groups are always
    # "accepted", and the server_default grandfathers every pre-existing thread in.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'accepted'"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Denormalised so the conversation list can sort by recency without joining every
    # message. Maintained on send.
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationParticipant(Base):
    """Who is in a thread, and how far they have read.

    Membership IS the access rule: every read and write checks for a row here, so a
    conversation is invisible to anyone not in it.
    """

    __tablename__ = "conversation_participants"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Read receipts are per participant, as a timestamp rather than a per-message row: unread
    # counts become "messages after this instant", which stays cheap as history grows.
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL, not CASCADE: deleting a user must not silently rewrite a conversation by
    # removing their side of it. The message survives, attributed to a former colleague.
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Soft delete: the row stays so the thread keeps its shape, and the body is not returned.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Every read is "this conversation, newest first" or "this conversation, after
        # timestamp X" (the poll). One composite index serves both.
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

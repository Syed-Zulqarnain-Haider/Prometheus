"""Conversation and message operations.

Access rule, applied everywhere: you can see a conversation if and only if you have a
participant row in it. A non-participant gets 404, never 403 - the same convention the rest
of the platform uses, so probing cannot distinguish "exists but not yours" from "does not
exist".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User, UserAvatar
from app.models.messaging import Conversation, ConversationParticipant, Message
from app.schemas.messaging import (
    ConversationList,
    ConversationOut,
    ConversationPerson,
    MessageOut,
    MessagePage,
)
from app.services import presence_service

# How much of the last message the conversation list shows.
PREVIEW_CHARS = 120
DEFAULT_PAGE = 50
MAX_PAGE = 200


def direct_key(a: uuid.UUID, b: uuid.UUID) -> str:
    """A stable identity for the pair, independent of who opened the thread."""
    return ":".join(sorted([str(a), str(b)]))


async def _require_participant(
    db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> ConversationParticipant:
    row = await db.get(ConversationParticipant, (conversation_id, user_id))
    if row is None:
        # Deliberately indistinguishable from a conversation that does not exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return row


async def get_or_create_direct(
    db: AsyncSession, me: uuid.UUID, other: uuid.UUID
) -> tuple[Conversation, bool]:
    """Return the direct thread between two people, creating it once. (thread, created)."""
    if me == other:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot message yourself")

    target = await db.get(User, other)
    if target is None or not target.is_active:
        # Same 404 convention: an inactive account is not a messageable person.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")

    key = direct_key(me, other)
    existing = (
        await db.execute(select(Conversation).where(Conversation.direct_key == key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    conversation = Conversation(kind="direct", direct_key=key, created_by=me)
    db.add(conversation)
    await db.flush()  # assign the id before adding participants
    db.add_all(
        [
            ConversationParticipant(conversation_id=conversation.id, user_id=me),
            ConversationParticipant(conversation_id=conversation.id, user_id=other),
        ]
    )
    await db.commit()
    await db.refresh(conversation)
    return conversation, True


async def _people_for(
    db: AsyncSession, redis: Redis, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ConversationPerson]:
    if not user_ids:
        return {}
    users = list((await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all())
    avatar_ids = {
        row[0]
        for row in (
            await db.execute(select(UserAvatar.user_id).where(UserAvatar.user_id.in_(user_ids)))
        ).all()
    }
    live = await presence_service.statuses(redis, [user.id for user in users])
    return {
        user.id: ConversationPerson(
            user_id=user.id,
            display_name=user.display_name,
            email=user.email,
            job_title=user.job_title,
            has_avatar=user.id in avatar_ids,
            status=presence_service.classify(live.get(user.id, False), user.last_seen_at),
            last_seen_at=user.last_seen_at,
        )
        for user in users
    }


async def list_conversations(db: AsyncSession, redis: Redis, me: uuid.UUID) -> ConversationList:
    """Every thread the caller is in, newest activity first, with unread counts."""
    mine = (
        await db.execute(
            select(ConversationParticipant).where(ConversationParticipant.user_id == me)
        )
    ).scalars()
    memberships = {row.conversation_id: row for row in mine}
    if not memberships:
        return ConversationList(conversations=[], unread_total=0)

    ids = list(memberships)
    conversations = list(
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.id.in_(ids))
                .order_by(
                    Conversation.last_message_at.desc().nullslast(),
                    Conversation.created_at.desc(),
                )
            )
        )
        .scalars()
        .all()
    )

    # Everyone else in those threads, in one query rather than one per conversation.
    others = list(
        (
            await db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id.in_(ids),
                    ConversationParticipant.user_id != me,
                )
            )
        )
        .scalars()
        .all()
    )
    people = await _people_for(db, redis, [row.user_id for row in others])
    by_conversation: dict[uuid.UUID, list[ConversationPerson]] = {}
    for row in others:
        person = people.get(row.user_id)
        if person is not None:
            by_conversation.setdefault(row.conversation_id, []).append(person)

    # Last message per conversation, and unread counts, both in a single pass each.
    last_rows = (
        await db.execute(
            select(Message.conversation_id, Message.body, Message.sender_id, Message.created_at)
            .where(Message.conversation_id.in_(ids), Message.deleted_at.is_(None))
            .order_by(Message.conversation_id, Message.created_at.desc())
            .distinct(Message.conversation_id)
        )
    ).all()
    last_by_conversation = {row[0]: row for row in last_rows}

    out: list[ConversationOut] = []
    unread_total = 0
    for conversation in conversations:
        membership = memberships[conversation.id]
        unread = await _unread_count(db, conversation.id, me, membership.last_read_at)
        unread_total += unread
        last = last_by_conversation.get(conversation.id)
        preview = None
        last_mine = False
        if last is not None:
            body = last[1]
            preview = body[:PREVIEW_CHARS] + ("..." if len(body) > PREVIEW_CHARS else "")
            last_mine = last[2] == me
        out.append(
            ConversationOut(
                id=conversation.id,
                kind=conversation.kind,
                title=conversation.title,
                participants=by_conversation.get(conversation.id, []),
                last_message_at=conversation.last_message_at,
                last_message_preview=preview,
                last_message_mine=last_mine,
                unread=unread,
            )
        )
    return ConversationList(conversations=out, unread_total=unread_total)


async def _unread_count(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    me: uuid.UUID,
    last_read_at: datetime | None,
) -> int:
    """Messages from other people after the caller's read mark. Your own never count."""
    stmt = (
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
            Message.sender_id != me,
        )
    )
    if last_read_at is not None:
        stmt = stmt.where(Message.created_at > last_read_at)
    return int((await db.execute(stmt)).scalar_one())


async def list_messages(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    me: uuid.UUID,
    *,
    after: datetime | None = None,
    limit: int = DEFAULT_PAGE,
) -> MessagePage:
    """Messages in a thread, oldest first.

    ``after`` is what makes polling cheap: the client asks only for what has arrived since
    its newest message, so a quiet thread costs an empty result rather than a full page.
    """
    await _require_participant(db, conversation_id, me)
    limit = max(1, min(limit, MAX_PAGE))

    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if after is not None:
        stmt = stmt.where(Message.created_at > after).order_by(Message.created_at).limit(limit)
        rows = list((await db.execute(stmt)).scalars().all())
    else:
        # Newest N, then flipped: the client wants the tail of the thread, in reading order.
        stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
        rows = list(reversed(list((await db.execute(stmt)).scalars().all())))

    senders = await _sender_names(db, [row.sender_id for row in rows if row.sender_id])
    messages = [
        MessageOut(
            id=row.id,
            conversation_id=row.conversation_id,
            sender_id=row.sender_id,
            sender_name=senders.get(row.sender_id) if row.sender_id else None,
            # A deleted message keeps its place in the thread but never returns its text.
            body="" if row.deleted_at is not None else row.body,
            created_at=row.created_at,
            edited_at=row.edited_at,
            deleted=row.deleted_at is not None,
            mine=row.sender_id == me,
        )
        for row in rows
    ]
    return MessagePage(
        messages=messages,
        latest_at=messages[-1].created_at if messages else after,
    )


async def _sender_names(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    unique = list(set(ids))
    if not unique:
        return {}
    rows = (
        await db.execute(select(User.id, User.display_name, User.email).where(User.id.in_(unique)))
    ).all()
    return {row[0]: row[1] or row[2].split("@", 1)[0] for row in rows}


async def send_message(
    db: AsyncSession, conversation_id: uuid.UUID, me: uuid.UUID, body: str
) -> MessageOut:
    await _require_participant(db, conversation_id, me)

    message = Message(conversation_id=conversation_id, sender_id=me, body=body)
    db.add(message)
    now = datetime.now(UTC)
    await db.execute(
        update(Conversation).where(Conversation.id == conversation_id).values(last_message_at=now)
    )
    # Sending is also reading: otherwise your own message would leave the thread showing
    # unread to you.
    await db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me,
        )
        .values(last_read_at=now)
    )
    await db.commit()
    await db.refresh(message)

    names = await _sender_names(db, [me])
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=me,
        sender_name=names.get(me),
        body=message.body,
        created_at=message.created_at,
        edited_at=None,
        deleted=False,
        mine=True,
    )


async def mark_read(db: AsyncSession, conversation_id: uuid.UUID, me: uuid.UUID) -> datetime:
    await _require_participant(db, conversation_id, me)
    now = datetime.now(UTC)
    await db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me,
        )
        .values(last_read_at=now)
    )
    await db.commit()
    return now


async def delete_message(db: AsyncSession, message_id: uuid.UUID, me: uuid.UUID) -> None:
    """Soft-delete your own message. Someone else's is not yours to remove."""
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    await _require_participant(db, message.conversation_id, me)
    if message.sender_id != me:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own messages")
    message.deleted_at = datetime.now(UTC)
    await db.commit()

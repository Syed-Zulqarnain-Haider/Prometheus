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
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
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

    # A brand-new direct thread is a REQUEST: nobody can message until the other person
    # accepts. (Pre-existing threads were grandfathered to "accepted" by the migration.)
    conversation = Conversation(
        kind="direct", direct_key=key, created_by=me, status="pending", requested_by=me
    )
    db.add(conversation)
    try:
        await db.flush()  # assign the id before adding participants
        db.add_all(
            [
                ConversationParticipant(conversation_id=conversation.id, user_id=me),
                ConversationParticipant(conversation_id=conversation.id, user_id=other),
            ]
        )
        await db.commit()
    except IntegrityError:
        # Two people opened the same DM at the same moment; the unique direct_key makes
        # one of them the loser. Losing the race means the thread exists - return it.
        await db.rollback()
        won_by_other = (
            await db.execute(select(Conversation).where(Conversation.direct_key == key))
        ).scalar_one_or_none()
        if won_by_other is not None:
            return won_by_other, False
        raise  # a different integrity failure - surface it
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
            # id as tiebreaker: created_at is transaction-start time, so two messages in
            # one transaction share it and DISTINCT ON would pick nondeterministically.
            .order_by(Message.conversation_id, Message.created_at.desc(), Message.id.desc())
            .distinct(Message.conversation_id)
        )
    ).all()
    last_by_conversation = {row[0]: row for row in last_rows}

    # Unread counts for EVERY thread in one grouped query, not one COUNT per thread: the
    # list polls every 15s per user, and the per-thread version cost N sequential round
    # trips on each poll.
    unread_stmt = (
        select(Message.conversation_id, func.count())
        .join(
            ConversationParticipant,
            (ConversationParticipant.conversation_id == Message.conversation_id)
            & (ConversationParticipant.user_id == me),
        )
        .where(
            Message.conversation_id.in_(ids),
            Message.deleted_at.is_(None),
            Message.sender_id != me,
            (ConversationParticipant.last_read_at.is_(None))
            | (Message.created_at > ConversationParticipant.last_read_at),
        )
        .group_by(Message.conversation_id)
    )
    unread_by_conversation = dict((await db.execute(unread_stmt)).all())

    out: list[ConversationOut] = []
    unread_total = 0
    for conversation in conversations:
        unread = int(unread_by_conversation.get(conversation.id, 0))
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
                status="pending" if conversation.status == "pending" else "accepted",
                requested_by_me=conversation.requested_by == me,
            )
        )
    return ConversationList(conversations=out, unread_total=unread_total)


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

    # Delivery watermarks for the caller's own bubbles: the OTHER participants' read
    # markers and last-active stamps, reduced with min() so a group state is only reached
    # when every member has reached it. Two scalars per page, not per message.
    watermark_rows = (
        await db.execute(
            select(ConversationParticipant.last_read_at, User.last_seen_at)
            .join(User, User.id == ConversationParticipant.user_id)
            .where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id != me,
            )
        )
    ).all()
    read_marks = [row[0] for row in watermark_rows]
    seen_marks = [row[1] for row in watermark_rows]
    all_read_at = min(read_marks) if read_marks and all(m is not None for m in read_marks) else None
    all_seen_at = min(seen_marks) if seen_marks and all(m is not None for m in seen_marks) else None

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
            receipt=(
                None
                if row.sender_id != me
                else "read"
                if all_read_at is not None and all_read_at >= row.created_at
                else "delivered"
                if all_seen_at is not None and all_seen_at >= row.created_at
                else "sent"
            ),
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
    db: AsyncSession,
    conversation_id: uuid.UUID,
    me: uuid.UUID,
    body: str,
    mentions: list[uuid.UUID] | None = None,
) -> MessageOut:
    await _require_participant(db, conversation_id, me)

    # The contact-request gate: a pending direct thread carries no messages in either
    # direction until it is accepted. 403, not 404 - the caller IS a participant, the
    # thread just is not open yet.
    conversation = await db.get(Conversation, conversation_id)
    if conversation is not None and conversation.status != "accepted":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This chat request has not been accepted yet"
        )

    # Mentions may only point INTO the thread: anything else is dropped silently rather
    # than becoming a side channel for pinging arbitrary users.
    if mentions:
        member_rows = (
            await db.execute(
                select(ConversationParticipant.user_id).where(
                    ConversationParticipant.conversation_id == conversation_id
                )
            )
        ).all()
        members = {row[0] for row in member_rows}
        mentions = [user_id for user_id in set(mentions) if user_id in members and user_id != me]

    message = Message(conversation_id=conversation_id, sender_id=me, body=body)
    db.add(message)
    # func.now(): message rows are stamped by the DATABASE clock (server_default), so the
    # denormalised copies must come from the same clock - app-clock skew here made fresh
    # messages read as unread (or hid them) depending on which clock ran ahead.
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_message_at=func.now())
    )
    # Sending is also reading: otherwise your own message would leave the thread showing
    # unread to you.
    await db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me,
        )
        .values(last_read_at=func.now())
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
        receipt="sent",
    )


async def get_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> Conversation | None:
    """Fetch a thread row (callers do their own membership check first)."""
    return await db.get(Conversation, conversation_id)


async def accept_direct(db: AsyncSession, conversation_id: uuid.UUID, me: uuid.UUID) -> None:
    """Accept a pending chat request. Only the person who RECEIVED it can accept."""
    await _require_participant(db, conversation_id, me)
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.kind != "direct":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    if conversation.status == "accepted":
        return  # idempotent - accepting twice is not an error
    if conversation.requested_by == me:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Waiting for the other person to accept your request"
        )
    conversation.status = "accepted"
    await db.commit()


async def remove_direct(db: AsyncSession, conversation_id: uuid.UUID, me: uuid.UUID) -> None:
    """Remove a direct thread: declines a received request, cancels a sent one, or
    disconnects an accepted contact.

    A thread that never carried a message is hard-deleted, which frees its unique
    ``direct_key`` so the pair can start fresh later. A thread WITH history is not:
    one participant must never be able to erase the other's messages and the oversight
    record along with them - every other deletion on this platform is non-destructive,
    and this is the one path a user could otherwise use to destroy evidence. There, the
    caller simply detaches; the conversation is removed once nobody is left in it.
    """
    await _require_participant(db, conversation_id, me)
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.kind != "direct":
        # Groups leave via leave_conversation(); this path is for direct contacts.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    has_history = (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
    ).scalar_one()
    if not has_history:
        await db.delete(conversation)
        await db.commit()
        return

    await db.execute(
        delete(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me,
        )
    )
    remaining = (
        await db.execute(
            select(func.count())
            .select_from(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == conversation_id)
        )
    ).scalar_one()
    if not remaining:
        # Both sides have walked away - nothing is being hidden from anyone now.
        await db.delete(conversation)
    await db.commit()


async def leave_conversation(db: AsyncSession, conversation_id: uuid.UUID, me: uuid.UUID) -> None:
    """Leave a group. Without this there was no way out of a group someone added you to.

    The thread and its history survive for the members who remain (and for oversight);
    only when the last member leaves is it removed.
    """
    await _require_participant(db, conversation_id, me)
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.kind != "group":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    await db.execute(
        delete(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == me,
        )
    )
    remaining = (
        await db.execute(
            select(func.count())
            .select_from(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == conversation_id)
        )
    ).scalar_one()
    if not remaining:
        await db.delete(conversation)
    await db.commit()


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
    # Keep the denormalised recency stamp truthful: if the deleted message WAS the latest,
    # the conversation must sort (and preview) by the newest surviving one.
    latest = (
        await db.execute(
            select(func.max(Message.created_at)).where(
                Message.conversation_id == message.conversation_id,
                Message.deleted_at.is_(None),
                Message.id != message.id,
            )
        )
    ).scalar_one_or_none()
    await db.execute(
        update(Conversation)
        .where(Conversation.id == message.conversation_id)
        .values(last_message_at=latest)
    )
    await db.commit()


# ── Admin oversight (owner decision: admins can see all chats) ───────────────────


async def admin_list_conversations(db: AsyncSession, redis: Redis) -> list[dict[str, object]]:
    """Every conversation on the platform, for administrative oversight.

    Read-only by design: there is deliberately no admin send/delete here - oversight is
    seeing, not impersonating. Callers must hold admin_panel (enforced at the route), and
    every use is audit-logged so oversight itself leaves a trail.
    """
    conversations = list(
        (
            await db.execute(
                select(Conversation).order_by(
                    Conversation.last_message_at.desc().nullslast(),
                    Conversation.created_at.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    ids = [conversation.id for conversation in conversations]
    if not ids:
        return []

    participants = list(
        (
            await db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id.in_(ids)
                )
            )
        )
        .scalars()
        .all()
    )
    people = await _people_for(db, redis, [row.user_id for row in participants])
    by_conversation: dict[uuid.UUID, list[ConversationPerson]] = {}
    for row in participants:
        person = people.get(row.user_id)
        if person is not None:
            by_conversation.setdefault(row.conversation_id, []).append(person)

    counts = dict(
        (
            await db.execute(
                select(Message.conversation_id, func.count())
                .where(Message.conversation_id.in_(ids), Message.deleted_at.is_(None))
                .group_by(Message.conversation_id)
            )
        ).all()
    )

    out: list[dict[str, object]] = []
    for conversation in conversations:
        out.append(
            {
                "id": conversation.id,
                "kind": conversation.kind,
                "title": conversation.title,
                "participants": by_conversation.get(conversation.id, []),
                "last_message_at": conversation.last_message_at,
                "last_message_preview": None,
                "last_message_mine": False,
                "unread": 0,
                "status": "pending" if conversation.status == "pending" else "accepted",
                "message_count": int(counts.get(conversation.id, 0)),
            }
        )
    return out


async def admin_list_messages(
    db: AsyncSession, conversation_id: uuid.UUID, *, limit: int = DEFAULT_PAGE
) -> MessagePage:
    """A thread's messages for oversight - no participant check, admin-gated at the route."""
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    limit = max(1, min(limit, MAX_PAGE))
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(list((await db.execute(stmt)).scalars().all())))
    senders = await _sender_names(db, [row.sender_id for row in rows if row.sender_id])
    messages = [
        MessageOut(
            id=row.id,
            conversation_id=row.conversation_id,
            sender_id=row.sender_id,
            sender_name=senders.get(row.sender_id) if row.sender_id else None,
            body="" if row.deleted_at is not None else row.body,
            created_at=row.created_at,
            edited_at=row.edited_at,
            deleted=row.deleted_at is not None,
            mine=False,
        )
        for row in rows
    ]
    return MessagePage(messages=messages, latest_at=messages[-1].created_at if messages else None)


async def create_group(
    db: AsyncSession, me: uuid.UUID, title: str, member_ids: list[uuid.UUID]
) -> Conversation:
    """A named thread with chosen members. The creator is always a member."""
    wanted = {user_id for user_id in member_ids if user_id != me}
    if not wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A group needs at least one other person")
    found = (
        await db.execute(select(User.id).where(User.id.in_(wanted), User.is_active.is_(True)))
    ).all()
    active_ids = {row[0] for row in found}
    missing = wanted - active_ids
    if missing:
        # Same 404 convention as everywhere else - do not confirm which ids exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")

    conversation = Conversation(kind="group", title=title, created_by=me)
    db.add(conversation)
    await db.flush()
    db.add_all(
        [
            ConversationParticipant(conversation_id=conversation.id, user_id=user_id)
            for user_id in (active_ids | {me})
        ]
    )
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def add_participant(db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Join a user to a thread (the invite-code path). Idempotent."""
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    if conversation.kind != "group":
        # A direct thread is exactly two people by definition; joining a third via a
        # leaked code must not silently turn it into a group.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only group chats accept invites")
    existing = await db.get(ConversationParticipant, (conversation_id, user_id))
    if existing is not None:
        return
    db.add(ConversationParticipant(conversation_id=conversation_id, user_id=user_id))
    await db.commit()


async def admin_delete_message(db: AsyncSession, message_id: uuid.UUID) -> None:
    """Soft-delete any single message (moderation). Audit-logged at the route."""
    message = await db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    message.deleted_at = datetime.now(UTC)
    await db.commit()


async def admin_delete_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    """Hard-delete a whole thread and its messages (CASCADE). Moderation tool: this is
    the storage-reclaiming path - soft-deleted rows keep their bytes, this does not."""
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    await db.delete(conversation)
    await db.commit()

"""Person-to-person messaging routes.

Real-time is done by polling, not WebSockets: the deployed nginx `/api/` location does not
set the Upgrade/Connection headers, so a socket would fail at the proxy. Polling with an
``after`` cursor keeps a quiet thread down to an empty response, and the transport can be
swapped later without changing these contracts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.schemas.messaging import (
    ConversationList,
    ConversationOut,
    DirectConversationCreate,
    MessageCreate,
    MessageOut,
    MessagePage,
    ReadResult,
)
from app.services import messaging_service
from app.services.audit import AuditDep

router = APIRouter(
    prefix="/chat",
    tags=["messaging"],
    dependencies=[Depends(enforce_rate_limit)],
)


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(
    context: CurrentUser, db: DbSession, redis: RedisClient
) -> ConversationList:
    """Your threads, newest activity first, each with unread count and live presence."""
    return await messaging_service.list_conversations(db, redis, context.user_id)


@router.post(
    "/conversations/direct",
    response_model=ConversationOut,
    status_code=status.HTTP_200_OK,
)
async def open_direct(
    request: Request,
    payload: DirectConversationCreate,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> ConversationOut:
    """Open a direct thread with someone, or return the existing one.

    Idempotent by design: opening the same conversation twice must never split the history
    into two threads, so this returns 200 whether or not it created anything.
    """
    conversation, created = await messaging_service.get_or_create_direct(
        db, context.user_id, payload.user_id
    )
    if created:
        await audit.write(
            user_id=context.user_id,
            action="conversation_created",
            resource=str(conversation.id),
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    listing = await messaging_service.list_conversations(db, redis, context.user_id)
    for item in listing.conversations:
        if item.id == conversation.id:
            return item
    # Unreachable in practice: the caller was just added as a participant.
    raise RuntimeError("conversation vanished immediately after creation")


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
async def list_messages(
    conversation_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    after: Annotated[
        datetime | None,
        Query(description="Return only messages created after this instant (the poll cursor)"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MessagePage:
    """Messages in a thread, oldest first. Not a participant reads as not found."""
    return await messaging_service.list_messages(
        db, conversation_id, context.user_id, after=after, limit=limit
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    context: CurrentUser,
    db: DbSession,
) -> MessageOut:
    """Send a message.

    Deliberately not audit-logged per message: the messages table IS the record, and
    duplicating every line into the audit log would bury the security events it exists for.
    """
    return await messaging_service.send_message(db, conversation_id, context.user_id, payload.body)


@router.post("/conversations/{conversation_id}/read", response_model=ReadResult)
async def mark_read(conversation_id: uuid.UUID, context: CurrentUser, db: DbSession) -> ReadResult:
    """Mark everything in this thread as read up to now."""
    read_at = await messaging_service.mark_read(db, conversation_id, context.user_id)
    return ReadResult(conversation_id=conversation_id, last_read_at=read_at)


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(message_id: uuid.UUID, context: CurrentUser, db: DbSession) -> Response:
    """Delete one of your own messages. It keeps its place in the thread, without its text."""
    await messaging_service.delete_message(db, message_id, context.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

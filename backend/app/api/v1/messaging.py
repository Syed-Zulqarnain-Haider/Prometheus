"""Person-to-person messaging routes.

Real-time is done by polling, not WebSockets: the deployed nginx `/api/` location does not
set the Upgrade/Connection headers, so a socket would fail at the proxy. Polling with an
``after`` cursor keeps a quiet thread down to an empty response, and the transport can be
swapped later without changing these contracts.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.deps import CurrentUser, DbSession, RedisClient, require_capability
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models.messaging import ConversationParticipant
from app.schemas.messaging import (
    AdminConversationList,
    AdminConversationOut,
    ConversationList,
    ConversationOut,
    DirectConversationCreate,
    GroupCreate,
    InviteCode,
    JoinByCode,
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
    return await messaging_service.send_message(
        db, conversation_id, context.user_id, payload.body, mentions=payload.mentions
    )


@router.post("/conversations/{conversation_id}/accept", response_model=ConversationOut)
async def accept_request(
    request: Request,
    conversation_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> ConversationOut:
    """Accept a pending chat request. Only the requested person can; then both can talk."""
    await messaging_service.accept_direct(db, conversation_id, context.user_id)
    await audit.write(
        user_id=context.user_id,
        action="chat_request_accepted",
        resource=str(conversation_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    listing = await messaging_service.list_conversations(db, redis, context.user_id)
    for item in listing.conversations:
        if item.id == conversation_id:
            return item
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    """Remove a direct contact: declines a received request, cancels a sent one, or
    disconnects an existing contact. Either participant may do it. Audit-logged."""
    await messaging_service.remove_direct(db, conversation_id, context.user_id)
    await audit.write(
        user_id=context.user_id,
        action="chat_contact_removed",
        resource=str(conversation_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_group(
    request: Request,
    conversation_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    """Leave a group you were added to. The thread survives for whoever remains."""
    await messaging_service.leave_conversation(db, conversation_id, context.user_id)
    await audit.write(
        user_id=context.user_id,
        action="chat_group_left",
        resource=str(conversation_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/read", response_model=ReadResult)
async def mark_read(conversation_id: uuid.UUID, context: CurrentUser, db: DbSession) -> ReadResult:
    """Mark everything in this thread as read up to now."""
    read_at = await messaging_service.mark_read(db, conversation_id, context.user_id)
    return ReadResult(conversation_id=conversation_id, last_read_at=read_at)


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    request: Request,
    message_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    """Delete one of your own messages. It keeps its place in the thread, without its text."""
    await messaging_service.delete_message(db, message_id, context.user_id)
    # Sends are deliberately not audited (the messages table IS that record), but a
    # DESTRUCTIVE action is a different class and leaves a trail like every other one.
    await audit.write(
        user_id=context.user_id,
        action="chat_message_deleted",
        resource=str(message_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Groups + single-use invite codes ─────────────────────────────────────────────

_INVITE_KEY = "chatinvite:{code}"
INVITE_TTL_SECONDS = 15 * 60


@router.post("/groups", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    request: Request,
    payload: GroupCreate,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> ConversationOut:
    """Create a named group chat with chosen members."""
    conversation = await messaging_service.create_group(
        db, context.user_id, payload.title, payload.member_ids
    )
    await audit.write(
        user_id=context.user_id,
        action="group_created",
        resource=str(conversation.id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    listing = await messaging_service.list_conversations(db, redis, context.user_id)
    for item in listing.conversations:
        if item.id == conversation.id:
            return item
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Group creation failed")


@router.post("/conversations/{conversation_id}/invite", response_model=InviteCode)
async def create_invite(
    request: Request,
    conversation_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> InviteCode:
    """Mint a single-use invite code for a group (owner decision on the whole flow):
    15-minute expiry, one use, one person - Redis TTL enforces the expiry and an atomic
    GETDEL at redemption enforces single use even under concurrent attempts. Minting a
    new code does NOT invalidate an unexpired old one; each is its own one-shot."""
    membership = await db.get(ConversationParticipant, (conversation_id, context.user_id))
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    # Reject a direct thread HERE rather than at redemption: /join consumes the code
    # atomically before add_participant refuses, which burned the one-shot code and
    # handed the redeemer an error for a code that was never valid to begin with.
    conversation = await messaging_service.get_conversation(db, conversation_id)
    if conversation is None or conversation.kind != "group":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only group chats accept invites")
    # 8 hex chars from a CSPRNG: 4 billion codes against a 15-minute window and a
    # rate-limited endpoint - and a code is worthless without also being authenticated.
    code = secrets.token_hex(4).upper()
    await redis.set(_INVITE_KEY.format(code=code), str(conversation_id), ex=INVITE_TTL_SECONDS)
    await audit.write(
        user_id=context.user_id,
        action="chat_invite_created",
        resource=str(conversation_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return InviteCode(code=code, expires_in_seconds=INVITE_TTL_SECONDS)


@router.post("/join", response_model=ConversationOut)
async def join_by_code(
    request: Request,
    payload: JoinByCode,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> ConversationOut:
    """Redeem an invite code. GETDEL makes redemption atomic: of two people racing the
    same code, exactly one wins; expiry has already been enforced by the key's TTL."""
    raw = await redis.getdel(_INVITE_KEY.format(code=payload.code.strip().upper()))
    if raw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That code is invalid or has expired")
    joined_id = uuid.UUID(raw.decode() if isinstance(raw, bytes) else raw)
    await messaging_service.add_participant(db, joined_id, context.user_id)
    await audit.write(
        user_id=context.user_id,
        action="chat_joined_by_code",
        resource=str(joined_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    listing = await messaging_service.list_conversations(db, redis, context.user_id)
    for item in listing.conversations:
        if item.id == joined_id:
            return item
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Join failed")


# ── Admin oversight (owner decision: admins can read all chats) ──────────────────
# Read-only: there is deliberately no admin send/edit/delete - oversight is seeing, not
# impersonating. Every oversight read is audit-logged, so looking itself leaves a trail
# that other admins can review.

_admin_only = require_capability("admin_panel")


@router.get(
    "/admin/conversations",
    response_model=AdminConversationList,
    dependencies=[Depends(_admin_only)],
)
async def admin_conversations(
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> AdminConversationList:
    """Every conversation on the platform, for administrative oversight."""
    rows = await messaging_service.admin_list_conversations(db, redis)
    await audit.write(
        user_id=context.user_id,
        action="chat_oversight_list",
        resource="all",
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AdminConversationList(
        conversations=[AdminConversationOut.model_validate(row) for row in rows]
    )


@router.get(
    "/admin/conversations/{conversation_id}/messages",
    response_model=MessagePage,
    dependencies=[Depends(_admin_only)],
)
async def admin_messages(
    request: Request,
    conversation_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
) -> MessagePage:
    """One thread's messages, read-only, for oversight. Audit-logged per view."""
    page = await messaging_service.admin_list_messages(db, conversation_id, limit=limit)
    await audit.write(
        user_id=context.user_id,
        action="chat_oversight_read",
        resource=str(conversation_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return page


@router.delete(
    "/admin/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_only)],
)
async def admin_remove_message(
    request: Request,
    message_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    """Moderation: soft-delete anyone's message. Audit-logged."""
    await messaging_service.admin_delete_message(db, message_id)
    await audit.write(
        user_id=context.user_id,
        action="chat_message_removed_by_admin",
        resource=str(message_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/admin/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_only)],
)
async def admin_remove_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> Response:
    """Moderation: HARD-delete a whole thread and its messages. This is the
    storage-reclaiming path (soft deletes keep their bytes). Audit-logged."""
    await messaging_service.admin_delete_conversation(db, conversation_id)
    await audit.write(
        user_id=context.user_id,
        action="chat_conversation_removed_by_admin",
        resource=str(conversation_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

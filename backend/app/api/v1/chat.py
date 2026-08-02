"""Ask-your-data assistant routes.

``GET /chat/status`` tells the frontend whether to show the widget (feature enabled by an
admin AND an API key configured). ``POST /chat`` answers a question — rate-limited, audited,
and RBAC-safe: the assistant only ever reads data the caller is permitted to see (every
lookup runs through the caller's scoped QueryBuilder; there is no raw-SQL path).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.http import client_ip
from app.core.rate_limit import enforce_chat_rate_limit
from app.schemas.chat import ChatRequest, ChatResponse, ChatStatus, ProviderInfo
from app.services import chat_providers, chat_service, settings_service
from app.services.audit import AuditDep

logger = logging.getLogger("app.api.chat")

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/status", response_model=ChatStatus)
async def chat_status(context: CurrentUser, db: DbSession) -> ChatStatus:
    """Whether the assistant is usable for this caller, and which providers they can pick.
    Any authenticated user may ask; answers are always scoped to their own access."""
    settings = get_settings()
    configured = chat_service.is_configured(settings)
    enabled = bool(await settings_service.get_value(db, "chat_enabled"))
    providers = [
        ProviderInfo(id=p.id, label=p.label)
        for p in chat_providers.available_providers(settings)
    ]
    reason: str | None = None
    if not enabled:
        reason = "The assistant is turned off. An admin can enable it in Settings."
    elif not configured:
        reason = "The assistant is not configured (no LLM provider API key is set)."
    return ChatStatus(
        available=enabled and configured,
        configured=configured,
        enabled=enabled,
        providers=providers,
        reason=reason,
    )


@router.post(
    "",
    response_model=ChatResponse,
    dependencies=[Depends(enforce_chat_rate_limit)],
)
async def chat(
    body: ChatRequest,
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> ChatResponse:
    settings = get_settings()
    if not bool(await settings_service.get_value(db, "chat_enabled")):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant is turned off. An admin can enable it in Settings.",
        )
    if not chat_service.is_configured(settings):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant is not configured (no LLM provider API key is set).",
        )

    # Validate the chosen provider up front so an unknown/unconfigured pick is a clean 400,
    # not a 502 out of the loop.
    try:
        provider = chat_providers.resolve(settings, body.provider)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    try:
        answer = await chat_service.answer_question(
            db, context, settings, body.messages, provider_id=provider.id
        )
    except Exception:  # noqa: BLE001 — never leak a stack trace / SDK error to the client.
        logger.exception("chat assistant failed (provider=%s)", provider.id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The assistant is temporarily unavailable. Please try again.",
        ) from None

    # Audit the question (append-only). Store only metadata — length, provider, and how many
    # scoped lookups ran — not the raw transcript.
    await audit.write(
        user_id=context.user_id,
        action="chat_query",
        resource="chat",
        detail={
            "turns": len(body.messages),
            "tool_calls": answer.tool_calls,
            "provider": answer.provider,
        },
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return ChatResponse(answer=answer.text, tool_calls=answer.tool_calls, provider=answer.provider)

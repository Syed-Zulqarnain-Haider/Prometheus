"""Shared FastAPI dependencies — primarily the authenticated user context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import (
    InvalidTokenError,
    TokenVerifier,
    bearer_scheme,
    get_token_verifier,
)
from app.schemas.auth import UserContext
from app.services.auth import (
    USER_CONTEXT_TTL_SECONDS,
    resolve_user_context,
    user_context_cache_key,
)


async def get_user_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cache: Annotated[Redis, Depends(get_redis)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> UserContext:
    """Verify the bearer token and resolve the caller's RBAC context.

    Resolved contexts are cached in Redis for 5 minutes. Failure modes:
      * missing / malformed / unverifiable token -> 401
      * verified token but no provisioned account -> 401
      * provisioned but inactive account          -> 403
      * provisioned but access expired            -> 403  (checked live, every request)
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing authentication token")

    try:
        decoded = verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token") from exc

    firebase_uid = decoded.get("uid")
    if not firebase_uid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token")

    cache_key = user_context_cache_key(firebase_uid)
    cached = await cache.get(cache_key)
    if cached is not None:
        context = UserContext.model_validate_json(cached)
    else:
        resolved = await resolve_user_context(db, firebase_uid)
        if resolved is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "No account is provisioned for this identity",
            )
        if not resolved.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is inactive")
        context = resolved
        await cache.set(cache_key, context.model_dump_json(), ex=USER_CONTEXT_TTL_SECONDS)

    # Time-limited access: enforced on EVERY request (a context cached before the deadline
    # must not keep serving past it). An expired user is denied exactly like a deactivated
    # one — this holds even if the UI is bypassed.
    if context.access_expires_at is not None and context.access_expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access has expired")

    request.state.user_context = context
    return context


CurrentUser = Annotated[UserContext, Depends(get_user_context)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]


def require_capability(
    capability: str,
) -> Callable[[UserContext], Awaitable[UserContext]]:
    """Build a dependency that requires the caller to hold ``capability``.

    Usage: ``Depends(require_capability("export"))``. Returns the user context on
    success; raises 403 otherwise. Capabilities: export, share_report, admin_panel.
    """

    async def _dependency(context: CurrentUser) -> UserContext:
        if capability not in context.capabilities:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing required capability")
        return context

    return _dependency

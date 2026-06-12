"""Auth routes: session bootstrap and current-user info."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.database import get_db
from app.schemas.auth import UserContext
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP, honoring a single X-Forwarded-For hop from the edge."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/session", response_model=UserContext)
async def create_session(
    request: Request,
    context: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserContext:
    """Establish a session: record a login audit entry and return the context."""
    await record_audit(
        db,
        user_id=context.user_id,
        action="login",
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return context


@router.get("/me", response_model=UserContext)
async def read_me(context: CurrentUser) -> UserContext:
    """Return the caller's roles, metric groups, capabilities, and scopes."""
    return context

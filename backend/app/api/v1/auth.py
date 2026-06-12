"""Auth routes: session bootstrap and current-user info."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser
from app.core.http import client_ip
from app.schemas.auth import UserContext
from app.services.audit import AuditDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session", response_model=UserContext)
async def create_session(request: Request, context: CurrentUser, audit: AuditDep) -> UserContext:
    """Establish a session: record a login audit entry and return the context."""
    await audit.log_login(
        user_id=context.user_id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return context


@router.get("/me", response_model=UserContext)
async def read_me(context: CurrentUser) -> UserContext:
    """Return the caller's roles, metric groups, capabilities, and scopes."""
    return context

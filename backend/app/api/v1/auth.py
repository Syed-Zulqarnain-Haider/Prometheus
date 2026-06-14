"""Auth routes: session bootstrap and current-user info."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.http import client_ip
from app.models import User
from app.schemas.auth import DirectoryEntry, UserContext
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


@router.get("/directory", response_model=list[DirectoryEntry])
async def directory(context: CurrentUser, db: DbSession) -> list[DirectoryEntry]:
    """Active users (minus the caller) for picking report-share recipients.

    A minimal name/email directory — no roles or scopes are exposed. Recipients
    always view shared reports through their OWN RBAC, so this leaks nothing.
    """
    rows = (
        (
            await db.execute(
                select(User)
                .where(User.is_active.is_(True), User.id != context.user_id)
                .order_by(User.email)
            )
        )
        .scalars()
        .all()
    )
    return [
        DirectoryEntry(user_id=u.id, email=u.email, display_name=u.display_name) for u in rows
    ]

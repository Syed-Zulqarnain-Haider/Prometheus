"""Auth routes: session bootstrap and current-user info."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, VerifiedUser, require_capability
from app.core.http import client_ip
from app.core.rate_limit import enforce_access_request_rate_limit, enforce_rate_limit
from app.models import User
from app.schemas.access import AccessRequestStatus
from app.schemas.auth import DirectoryEntry, UserContext
from app.services import access_service
from app.services.audit import AuditDep

# Per-user rate limiting applies to the auth routes too (parity with every other
# router); each route resolves CurrentUser, so the limiter has the caller's id.
router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(enforce_rate_limit)])

# A SEPARATE /auth router WITHOUT the CurrentUser-based limiter — its routes serve
# authenticated-but-UNPROVISIONED identities (the main router's limiter resolves
# CurrentUser, which 401s them before the route runs).
public_router = APIRouter(prefix="/auth", tags=["auth"])


@public_router.post(
    "/access-request",
    response_model=AccessRequestStatus,
    dependencies=[Depends(enforce_access_request_rate_limit)],
)
async def request_access(
    identity: VerifiedUser,
    request: Request,
    db: DbSession,
    audit: AuditDep,
) -> AccessRequestStatus:
    """Lodge (or refresh) a pending access request for a verified-but-unprovisioned user.
    Idempotent by Firebase UID; grants ZERO access — an admin must approve. Audited."""
    req = await access_service.record_request(
        db,
        firebase_uid=identity.firebase_uid,
        email=identity.email,
        display_name=identity.display_name,
    )
    await audit.write(
        user_id=None,
        action="access_request",
        resource=identity.firebase_uid,
        detail={"email": identity.email},
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AccessRequestStatus(status=req.status)


# The share directory is only needed by users who can share reports; gating it on
# the share_report capability stops lower-privilege roles (e.g. viewer) from
# enumerating every user's email. Recipients still view shares through their OWN RBAC.
ShareUser = Annotated[UserContext, Depends(require_capability("share_report"))]


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
async def directory(context: ShareUser, db: DbSession) -> list[DirectoryEntry]:
    """Active users (minus the caller) for picking report-share recipients.

    Restricted to roles holding ``share_report`` (others get 403) — a minimal
    name/email directory, no roles or scopes exposed. Recipients always view
    shared reports through their OWN RBAC, so this leaks nothing extra.
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
    return [DirectoryEntry(user_id=u.id, email=u.email, display_name=u.display_name) for u in rows]

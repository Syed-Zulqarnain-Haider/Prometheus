"""Self-service account security: 2FA status, recent device activity, sign-out-everywhere."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.schemas.account import DeviceActivity, RevokeResult, SecurityStatus
from app.services import account_service
from app.services.audit import AuditDep
from app.services.auth import user_context_cache_key

router = APIRouter(prefix="/me", tags=["account"], dependencies=[Depends(enforce_rate_limit)])


@router.get("/security", response_model=SecurityStatus)
async def security(request: Request, context: CurrentUser, db: DbSession) -> SecurityStatus:
    """Whether this sign-in used 2FA, when sessions were last revoked, and recent devices."""
    devices = await account_service.recent_activity(db, context.user_id)
    return SecurityStatus(
        two_factor=bool(getattr(request.state, "two_factor", False)),
        sessions_revoked_at=context.sessions_revoked_at,
        devices=[DeviceActivity(**d) for d in devices],
    )


@router.post("/security/revoke-sessions", response_model=RevokeResult)
async def revoke_sessions(
    request: Request,
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    audit: AuditDep,
) -> RevokeResult:
    """Sign out of all devices. Stamps the revoke instant (tokens issued earlier are rejected
    live) and best-effort revokes Firebase refresh tokens. This request's own token was issued
    before 'now', so the caller is signed out too and must re-authenticate."""
    revoked_at = await account_service.revoke_sessions(db, context.user_id)
    # Bust the cached context so the new sessions_revoked_at takes effect on the very next request.
    await redis.delete(user_context_cache_key(context.firebase_uid))
    await audit.write(
        user_id=context.user_id,
        action="sessions_revoked",
        resource="self",
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return RevokeResult(revoked_at=revoked_at)

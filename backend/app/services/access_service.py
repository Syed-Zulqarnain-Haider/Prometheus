"""Access-request queue: record (idempotent), list pending, approve (provision), reject.

Recording a request NEVER provisions a user or grants a role — only ``approve`` does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccessRequest, User
from app.schemas.access import AccessRequestOut
from app.schemas.admin import ScopeIn, UserSummary
from app.services import admin_service


def _out(req: AccessRequest) -> AccessRequestOut:
    return AccessRequestOut(
        id=req.id,
        firebase_uid=req.firebase_uid,
        email=req.email,
        display_name=req.display_name,
        status=req.status,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


async def record_request(
    db: AsyncSession, *, firebase_uid: str, email: str, display_name: str | None
) -> AccessRequestOut:
    """Idempotent upsert by ``firebase_uid``: a repeat sign-in refreshes the existing row
    and re-opens a previously rejected one (status -> pending) — never a duplicate, and
    NEVER a user/role. Returns the (always-pending) request."""
    now = datetime.now(UTC)
    await db.execute(
        pg_insert(AccessRequest)
        .values(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[AccessRequest.firebase_uid],
            set_={
                "email": email,
                "display_name": display_name,
                "status": "pending",
                "updated_at": now,
                "decided_by": None,
                "decided_at": None,
            },
        )
    )
    await db.commit()
    row = await db.scalar(select(AccessRequest).where(AccessRequest.firebase_uid == firebase_uid))
    assert row is not None  # just upserted
    return _out(row)


async def list_pending(db: AsyncSession) -> list[AccessRequestOut]:
    rows = (
        (
            await db.execute(
                select(AccessRequest)
                .where(AccessRequest.status == "pending")
                .order_by(AccessRequest.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [_out(r) for r in rows]


async def approve(
    db: AsyncSession,
    request_id: uuid.UUID,
    *,
    roles: list[str],
    scopes: list[ScopeIn],
    access_expires_at: datetime | None,
    actor_id: uuid.UUID,
) -> tuple[UserSummary, str]:
    """Provision (or re-activate) the requester with the given role/scope/expiry and mark
    the request approved. Returns (user summary, firebase_uid). Raises LookupError if the request is
    missing. Never auto-grants admin — the admin chooses the roles explicitly."""
    req = await db.get(AccessRequest, request_id)
    if req is None:
        raise LookupError("access request not found")

    existing = await db.scalar(select(User).where(User.firebase_uid == req.firebase_uid))
    if existing is None:
        summary = await admin_service.create_user(
            db,
            firebase_uid=req.firebase_uid,
            email=req.email,
            display_name=req.display_name,
            roles=roles,
            scopes=scopes,
            created_by=actor_id,
            access_expires_at=access_expires_at,
        )
    else:
        summary = await admin_service.update_user(
            db,
            existing,
            display_name=existing.display_name,
            is_active=True,
            roles=roles,
            scopes=scopes,
            actor_id=actor_id,
            display_name_set=False,
            access_expires_at=access_expires_at,
            access_set=True,
        )

    req.status = "approved"
    req.decided_by = actor_id
    req.decided_at = datetime.now(UTC)
    await db.commit()
    return summary, req.firebase_uid


async def reject(db: AsyncSession, request_id: uuid.UUID, actor_id: uuid.UUID) -> AccessRequestOut:
    """Mark a request rejected (zero access; the identity may re-request by signing in
    again). Raises LookupError if missing."""
    req = await db.get(AccessRequest, request_id)
    if req is None:
        raise LookupError("access request not found")
    req.status = "rejected"
    req.decided_by = actor_id
    req.decided_at = datetime.now(UTC)
    await db.commit()
    return _out(req)

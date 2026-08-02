"""Self-service account security: recent device activity + 'sign out everywhere'.

Recent activity is derived from the append-only ``audit_log`` (login + api_query events),
grouped by device + network — an honest "where you've been active" view, not a fabricated
per-session store. Revocation stamps ``users.sessions_revoked_at`` (enforced live in
get_user_context) and best-effort revokes Firebase refresh tokens so the client must re-auth.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import cast as sa_cast
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

log = logging.getLogger("app.account")

# Activity actions worth showing as "sessions/devices" (ignore high-volume noise).
_ACTIVITY_ACTIONS = ("login", "api_query", "export", "chat_query")


async def recent_activity(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 10
) -> list[dict[str, Any]]:
    """Recent activity grouped by (user_agent, ip): last-seen + count, newest first."""
    ip_text = sa_cast(AuditLog.ip_address, TEXT).label("ip_text")
    stmt = (
        select(
            AuditLog.user_agent.label("user_agent"),
            ip_text,
            func.max(AuditLog.created_at).label("last_seen"),
            func.count().label("events"),
        )
        .where(AuditLog.user_id == user_id, AuditLog.action.in_(_ACTIVITY_ACTIONS))
        .group_by(AuditLog.user_agent, ip_text)
        .order_by(func.max(AuditLog.created_at).desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).mappings().all()
    return [
        {
            "user_agent": r["user_agent"],
            "ip_address": r["ip_text"],
            "last_seen": r["last_seen"],
            "events": int(r["events"]),
        }
        for r in rows
    ]


async def revoke_sessions(db: AsyncSession, user_id: uuid.UUID) -> datetime:
    """Sign the user out of every device: stamp sessions_revoked_at and best-effort revoke
    Firebase refresh tokens. Returns the revoke instant. Caller busts the cached context."""
    now = datetime.now(UTC)
    await db.execute(update(User).where(User.id == user_id).values(sessions_revoked_at=now))
    await db.commit()

    firebase_uid = await db.scalar(select(User.firebase_uid).where(User.id == user_id))
    if firebase_uid:
        _revoke_firebase(str(firebase_uid))
    return now


def _revoke_firebase(firebase_uid: str) -> None:
    """Best-effort Firebase refresh-token revocation. Never raises — server-side
    sessions_revoked_at already enforces the sign-out even if this can't run."""
    try:
        from firebase_admin import auth as firebase_auth

        firebase_auth.revoke_refresh_tokens(firebase_uid)
    except Exception:  # noqa: BLE001 — firebase may be unconfigured (local/tests)
        log.info("firebase refresh-token revoke skipped/failed for uid=%s", firebase_uid)

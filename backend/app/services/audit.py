"""Minimal audit-log writer.

The audit_log is append-only (INSERT only); the api_service DB role has no
UPDATE/DELETE on it. The full audit middleware arrives in a later step — this
helper covers the login event written by POST /auth/session.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record_audit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    ip: str | None = None,
    user_agent: str | None = None,
    resource: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append a single row to audit_log (caller is responsible for commit)."""
    await db.execute(
        insert(AuditLog).values(
            user_id=user_id,
            action=action,
            ip_address=ip,
            user_agent=user_agent,
            resource=resource,
            detail=detail,
        )
    )

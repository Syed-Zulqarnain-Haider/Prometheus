"""Audit service — append-only writes to ``audit_log``.

Design guarantees:
  * INSERT only (the api_service DB role has no UPDATE/DELETE on audit_log).
  * Writes happen in the service's OWN session/transaction, independent of the
    request's session, so an audit failure can never poison the request's
    transaction.
  * The service NEVER raises into the request path — any failure is logged and
    swallowed (log-and-continue). Audit is best-effort durability, not a reason
    to fail a user's request.

Explicit helpers exist for the common actions (login, export, admin); the API
middleware uses ``write(action="api_query", ...)`` for data routes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_sessionmaker
from app.models import AuditLog

logger = logging.getLogger("app.services.audit")


class AuditService:
    """Writes audit entries on independent, self-committing transactions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def write(
        self,
        *,
        user_id: uuid.UUID | None,
        action: str,
        resource: str | None = None,
        detail: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Append one audit row. Never raises — logs and continues on failure."""
        try:
            async with self._sessionmaker() as session:
                await session.execute(
                    insert(AuditLog).values(
                        user_id=user_id,
                        action=action,
                        resource=resource,
                        detail=detail,
                        ip_address=ip,
                        user_agent=user_agent,
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "Failed to write audit entry (action=%s, resource=%s)", action, resource
            )

    async def log_login(
        self,
        *,
        user_id: uuid.UUID,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self.write(user_id=user_id, action="login", ip=ip, user_agent=user_agent)

    async def log_export(
        self,
        *,
        user_id: uuid.UUID,
        resource: str,
        detail: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        await self.write(
            user_id=user_id,
            action="export",
            resource=resource,
            detail=detail,
            ip=ip,
            user_agent=user_agent,
        )

    async def log_admin_action(
        self,
        *,
        user_id: uuid.UUID,
        action: str,
        resource: str | None = None,
        detail: dict[str, Any] | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Log an administrative action. ``action`` is the specific admin verb."""
        await self.write(
            user_id=user_id,
            action=action,
            resource=resource,
            detail=detail,
            ip=ip,
            user_agent=user_agent,
        )


def get_audit_service(
    sessionmaker: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> AuditService:
    """FastAPI dependency providing an AuditService."""
    return AuditService(sessionmaker)


AuditDep = Annotated[AuditService, Depends(get_audit_service)]

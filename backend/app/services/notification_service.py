"""In-app notifications — creation (best-effort, never breaks a request) + RBAC-scoped reads.

Audience routing:
  * ``all``          — every user sees it.
  * ``admins``       — only users holding the ``admin_panel`` capability.
  * ``user:<uuid>``  — only that specific user.

Creation writes on its OWN session and swallows failures (like the audit service), so a
notification can never poison or fail the request that triggered it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_sessionmaker
from app.models import Notification, NotificationRead
from app.schemas.notifications import NotificationList, NotificationOut

logger = logging.getLogger("app.services.notifications")


async def create(
    *,
    type: str,
    title: str,
    body: str | None = None,
    audience: str = "all",
    actor_id: uuid.UUID | None = None,
    resource: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append a notification on an independent transaction. Never raises."""
    try:
        async with get_sessionmaker()() as session:
            session.add(
                Notification(
                    type=type,
                    title=title,
                    body=body,
                    audience=audience,
                    actor_user_id=actor_id,
                    resource=resource,
                    detail=detail,
                )
            )
            await session.commit()
    except Exception:
        logger.exception("Failed to write notification (type=%s)", type)


async def notify_admins(**kwargs: Any) -> None:
    await create(audience="admins", **kwargs)


async def notify_user(user_id: uuid.UUID, **kwargs: Any) -> None:
    await create(audience=f"user:{user_id}", **kwargs)


def _visible(user_id: uuid.UUID, is_admin: bool) -> Any:
    """SQL predicate for notifications this user may see."""
    conds = [Notification.audience == "all", Notification.audience == f"user:{user_id}"]
    if is_admin:
        conds.append(Notification.audience == "admins")
    return or_(*conds)


async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID, is_admin: bool, limit: int = 30
) -> NotificationList:
    """Most-recent visible notifications (with per-user read flag) + the unread count."""
    stmt = (
        select(Notification, NotificationRead.notification_id)
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            ),
        )
        .where(_visible(user_id, is_admin))
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        NotificationOut(
            id=n.id,
            created_at=n.created_at,
            type=n.type,
            title=n.title,
            body=n.body,
            resource=n.resource,
            detail=n.detail,
            read=read_id is not None,
        )
        for n, read_id in rows
    ]
    return NotificationList(items=items, unread=await unread_count(session, user_id, is_admin))


async def unread_count(session: AsyncSession, user_id: uuid.UUID, is_admin: bool) -> int:
    read_ids = select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(and_(_visible(user_id, is_admin), Notification.id.notin_(read_ids)))
    )
    return int((await session.execute(stmt)).scalar_one())


async def mark_read(session: AsyncSession, user_id: uuid.UUID, notification_id: int) -> None:
    await session.execute(
        pg_insert(NotificationRead)
        .values(notification_id=notification_id, user_id=user_id)
        .on_conflict_do_nothing()
    )
    await session.commit()


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID, is_admin: bool) -> None:
    """Mark every currently-visible unread notification as read for this user."""
    read_ids = select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)
    unread = (
        (
            await session.execute(
                select(Notification.id).where(
                    and_(_visible(user_id, is_admin), Notification.id.notin_(read_ids))
                )
            )
        )
        .scalars()
        .all()
    )
    for nid in unread:
        await session.execute(
            pg_insert(NotificationRead)
            .values(notification_id=nid, user_id=user_id)
            .on_conflict_do_nothing()
        )
    await session.commit()

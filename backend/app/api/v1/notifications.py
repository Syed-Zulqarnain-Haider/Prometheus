"""Notification routes — every authenticated user sees their RBAC-scoped notifications."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import enforce_rate_limit
from app.schemas.notifications import NotificationList
from app.services import notification_service

router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(enforce_rate_limit)]
)


@router.get("", response_model=NotificationList)
async def list_notifications(
    context: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> NotificationList:
    """This user's most recent notifications (RBAC-scoped) + unread count."""
    return await notification_service.list_for_user(
        db, context.user_id, "admin_panel" in context.capabilities, limit
    )


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(notification_id: int, context: CurrentUser, db: DbSession) -> None:
    """Mark one notification read for this user."""
    await notification_service.mark_read(db, context.user_id, notification_id)


@router.post("/read-all", status_code=204)
async def mark_all_read(context: CurrentUser, db: DbSession) -> None:
    """Mark all of this user's visible notifications read."""
    await notification_service.mark_all_read(
        db, context.user_id, "admin_panel" in context.capabilities
    )

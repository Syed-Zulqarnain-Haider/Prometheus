"""Announcement banner routes: everyone reads their own view; admins publish and retire."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text

from app.api.deps import CurrentUser, DbSession, require_capability
from app.core.http import client_ip
from app.core.rate_limit import enforce_rate_limit
from app.models.announcements import Announcement
from app.services.audit import AuditDep

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"],
    dependencies=[Depends(enforce_rate_limit)],
)

_admin_only = require_capability("admin_panel")

VALID_ROLES = {"admin", "executive", "pod_owner", "marketing", "finance", "viewer"}


class AnnouncementOut(BaseModel):
    id: uuid.UUID
    body: str
    level: Literal["info", "success", "warning", "critical"]
    audience_roles: list[str]
    cta_label: str | None = None
    cta_url: str | None = None
    is_active: bool
    expires_at: datetime | None
    created_at: datetime


class AnnouncementCreate(BaseModel):
    body: str = Field(min_length=1, max_length=500)
    level: Literal["info", "success", "warning", "critical"] = "info"
    # Empty = everyone. Role names are validated against the platform's fixed role set.
    audience_roles: list[str] = Field(default_factory=list, max_length=6)
    cta_label: str | None = Field(default=None, max_length=40)
    cta_url: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None

    @field_validator("body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Announcement cannot be empty")
        return trimmed

    @field_validator("cta_label", "cta_url")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        trimmed = (value or "").strip()
        return trimmed or None

    @field_validator("cta_url")
    @classmethod
    def _safe_url(cls, value: str | None) -> str | None:
        """Allow-list, not deny-list: an in-app path or an https:// URL, nothing else.

        The banner is rendered for every user on the platform, so a stored
        ``javascript:`` (or ``data:``) URL would be a persistent XSS with admin
        authorship. Rejecting anything outside the allow-list closes that entirely,
        and ``//evil.com`` is rejected too - it is protocol-relative, not a local path.
        """
        if value is None:
            return None
        if value.startswith("/") and not value.startswith("//"):
            return value
        if value.startswith("https://") and len(value) > len("https://"):
            return value
        raise ValueError("Link must be an in-app path starting with / or an https:// URL")

    @field_validator("audience_roles")
    @classmethod
    def _known_roles(cls, value: list[str]) -> list[str]:
        unknown = set(value) - VALID_ROLES
        if unknown:
            raise ValueError(f"Unknown roles: {', '.join(sorted(unknown))}")
        return sorted(set(value))


@router.get("/active", response_model=list[AnnouncementOut])
async def active_announcements(context: CurrentUser, db: DbSession) -> list[AnnouncementOut]:
    """The banners THIS caller should see: active, unexpired, and either aimed at everyone
    (empty audience) or at one of the caller's roles. Audience filtering happens here on
    the server - a client never receives a banner meant for someone else."""
    now = datetime.now(UTC)
    # The audience predicate runs in SQL, BEFORE the limit. Filtering in Python after a
    # LIMIT 10 meant ten banners aimed at other roles could push an everyone-banner off
    # the page entirely - the reader would simply never see it.
    rows = list(
        (
            await db.execute(
                select(Announcement)
                .where(
                    Announcement.is_active.is_(True),
                    (Announcement.expires_at.is_(None)) | (Announcement.expires_at > now),
                    (Announcement.audience_roles == text("'{}'"))
                    | (Announcement.audience_roles.overlap(list(context.roles))),
                )
                .order_by(Announcement.created_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    return [AnnouncementOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("", response_model=list[AnnouncementOut], dependencies=[Depends(_admin_only)])
async def all_announcements(db: DbSession) -> list[AnnouncementOut]:
    """Every announcement including retired ones - the admin management view."""
    rows = list(
        (await db.execute(select(Announcement).order_by(Announcement.created_at.desc()).limit(50)))
        .scalars()
        .all()
    )
    return [AnnouncementOut.model_validate(row, from_attributes=True) for row in rows]


@router.post(
    "",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def publish(
    request: Request,
    payload: AnnouncementCreate,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> AnnouncementOut:
    """Publish a banner. Audit-logged with its audience, like every admin action."""
    row = Announcement(
        body=payload.body,
        level=payload.level,
        audience_roles=payload.audience_roles,
        cta_label=payload.cta_label,
        cta_url=payload.cta_url,
        expires_at=payload.expires_at,
        created_by=context.user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await audit.write(
        user_id=context.user_id,
        action="announcement_published",
        resource=str(row.id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AnnouncementOut.model_validate(row, from_attributes=True)


@router.delete(
    "/{announcement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_only)],
)
async def retire(
    request: Request,
    announcement_id: uuid.UUID,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> None:
    """Retire a banner. A flag flip, not a delete - the record of what was announced
    survives for the audit trail."""
    row = await db.get(Announcement, announcement_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Announcement not found")
    row.is_active = False
    await db.commit()
    await audit.write(
        user_id=context.user_id,
        action="announcement_retired",
        resource=str(announcement_id),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

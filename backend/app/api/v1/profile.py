"""Profile, avatar and people-directory routes.

Mounted onto the existing ``/me`` account router (see ``account.py``) rather than registered
separately, so it inherits that router's rate limiting and needs no change to ``main.py``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.http import client_ip
from app.schemas.people import AvatarUploaded, PeopleList, ProfileOut, ProfileUpdate
from app.services import people_service
from app.services.audit import AuditDep

router = APIRouter()

# Avatars are personal data, so they must never be cached by a shared proxy. They do change
# rarely, hence a short private cache rather than none at all.
_AVATAR_CACHE_CONTROL = "private, max-age=300"


@router.get("/profile", response_model=ProfileOut, tags=["profile"])
async def read_profile(context: CurrentUser, db: DbSession) -> ProfileOut:
    """The signed-in user's own profile."""
    return await people_service.get_profile(db, context.user_id)


@router.put("/profile", response_model=ProfileOut, tags=["profile"])
async def update_profile(
    request: Request,
    payload: ProfileUpdate,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
) -> ProfileOut:
    """Update your own name, title, phone and timezone.

    Roles, scopes, email and active status are NOT settable here - those are administered.
    """
    profile = await people_service.update_profile(db, context.user_id, payload)
    await audit.write(
        user_id=context.user_id,
        action="profile_updated",
        resource="self",
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return profile


@router.post("/profile/avatar", response_model=AvatarUploaded, tags=["profile"])
async def upload_avatar(
    request: Request,
    context: CurrentUser,
    db: DbSession,
    audit: AuditDep,
    file: Annotated[UploadFile, File()],
) -> AvatarUploaded:
    """Upload a profile picture (PNG, JPEG, GIF or WEBP, up to 512 KB).

    The type is determined from the file's own bytes, not its declared content type.
    """
    # Bounded read: file.read() would buffer an arbitrarily large body into memory BEFORE
    # any size check ran, so an oversized upload is cut off at the limit instead. One extra
    # byte distinguishes "exactly at the limit" from "over it".
    data = await file.read(people_service.MAX_AVATAR_BYTES + 1)
    size, content_type = await people_service.set_avatar(db, context.user_id, data)
    await audit.write(
        user_id=context.user_id,
        action="avatar_updated",
        resource="self",
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return AvatarUploaded(has_avatar=True, bytes=size, content_type=content_type)


@router.delete("/profile/avatar", status_code=status.HTTP_204_NO_CONTENT, tags=["profile"])
async def remove_avatar(context: CurrentUser, db: DbSession) -> Response:
    """Remove your profile picture. Removing one you do not have is not an error."""
    await people_service.delete_avatar(db, context.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/people", response_model=PeopleList, tags=["people"])
async def list_people(
    context: CurrentUser,
    db: DbSession,
    redis: RedisClient,
    q: str | None = Query(default=None, max_length=100, description="Filter by name or email"),
) -> PeopleList:
    """Everyone who can be messaged, with live presence (online / away / offline).

    Last-login times are administrative detail and are returned only to admins.
    """
    return await people_service.list_people(
        db,
        redis,
        include_login_times="admin_panel" in context.capabilities,
        query=q,
    )


@router.get("/people/{user_id}/avatar", tags=["people"])
async def person_avatar(
    request: Request, user_id: uuid.UUID, context: CurrentUser, db: DbSession
) -> Response:
    """Another user's avatar image.

    Any signed-in user may fetch any colleague's picture - the directory already shows who
    exists, so the image carries nothing the caller cannot already see. A user without an
    avatar returns 404 so the client falls back to initials.
    """
    found = await people_service.get_avatar(db, user_id)
    if found is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    data, content_type, updated_at = found
    etag = f'"{user_id}-{int(updated_at.timestamp())}"'
    # Honour If-None-Match - emitting an ETag without checking it means the 304 path never
    # fires and the full image bytes are re-sent on every render.
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"Cache-Control": _AVATAR_CACHE_CONTROL, "ETag": etag},
        )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": _AVATAR_CACHE_CONTROL, "ETag": etag},
    )

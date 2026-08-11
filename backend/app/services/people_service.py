"""Profile reads/writes, avatar storage, and the people directory with live presence."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Role, User, UserAvatar, UserRole
from app.schemas.people import PeopleList, PersonOut, ProfileOut, ProfileUpdate
from app.services import presence_service

# Avatars live in Postgres rather than on disk. For ~50 users the storage is trivial, and it
# survives a container rebuild with no volume to configure or back up separately - the
# database is already backed up before every deploy.
MAX_AVATAR_BYTES = 512 * 1024

# Content type is taken from the BYTES, never from the client's header: a caller can label
# anything "image/png". Each entry is (magic prefix, canonical content type).
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def sniff_image_type(data: bytes) -> str:
    """Return the canonical content type, or raise 400 if these bytes are not an image.

    WEBP needs a two-part check: "RIFF" then "WEBP" four bytes later.
    """
    for magic, content_type in _MAGIC:
        if data.startswith(magic):
            return content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "That file is not a PNG, JPEG, GIF or WEBP image",
    )


async def _roles_by_user(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not user_ids:
        return {}
    rows = await db.execute(
        select(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(user_ids))
    )
    out: dict[uuid.UUID, list[str]] = {}
    for user_id, role_name in rows.all():
        out.setdefault(user_id, []).append(role_name)
    for names in out.values():
        names.sort()
    return out


async def _has_avatar(db: AsyncSession, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Which users have an avatar - selecting the id only, never the image bytes."""
    if not user_ids:
        return set()
    rows = await db.execute(select(UserAvatar.user_id).where(UserAvatar.user_id.in_(user_ids)))
    return {row[0] for row in rows.all()}


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> ProfileOut:
    user = await db.get(User, user_id)
    if user is None:
        # The caller authenticated, so this means the account was deleted mid-session.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    roles = (await _roles_by_user(db, [user_id])).get(user_id, [])
    avatars = await _has_avatar(db, [user_id])
    return ProfileOut(
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        display_name=user.display_name,
        job_title=user.job_title,
        phone=user.phone,
        timezone=user.timezone,
        has_avatar=user_id in avatars,
        roles=roles,
        last_login_at=user.last_login_at,
        last_seen_at=user.last_seen_at,
        created_at=user.created_at,
    )


async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, payload: ProfileUpdate
) -> ProfileOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    # Only fields the client actually SENT are applied - all fields are optional, so a
    # partial PUT (e.g. {"first_name": "X"}) must not silently wipe the other four.
    sent = payload.model_dump(exclude_unset=True)
    for field in ("first_name", "last_name", "job_title", "phone", "timezone"):
        if field in sent:
            setattr(user, field, sent[field])

    # display_name is what the rest of the app already shows (sharing, audit, chat). Keep it
    # in step with the real name when one is given, and fall back to the email local part so
    # a user is never rendered as a blank space.
    full = " ".join(p for p in (user.first_name, user.last_name) if p)
    user.display_name = full or user.email.split("@", 1)[0]

    await db.commit()
    return await get_profile(db, user_id)


async def set_avatar(db: AsyncSession, user_id: uuid.UUID, data: bytes) -> tuple[int, str]:
    """Validate and store an avatar. Returns (size, content type)."""
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Images must be {MAX_AVATAR_BYTES // 1024} KB or smaller",
        )
    content_type = sniff_image_type(data)

    await db.execute(
        pg_insert(UserAvatar)
        .values(user_id=user_id, content_type=content_type, data=data)
        .on_conflict_do_update(
            index_elements=[UserAvatar.user_id],
            set_={"content_type": content_type, "data": data},
        )
    )
    await db.commit()
    return len(data), content_type


async def get_avatar(db: AsyncSession, user_id: uuid.UUID) -> tuple[bytes, str, datetime] | None:
    avatar = await db.get(UserAvatar, user_id)
    if avatar is None:
        return None
    return avatar.data, avatar.content_type, avatar.updated_at


async def delete_avatar(db: AsyncSession, user_id: uuid.UUID) -> None:
    avatar = await db.get(UserAvatar, user_id)
    if avatar is not None:
        await db.delete(avatar)
        await db.commit()


async def list_people(
    db: AsyncSession,
    redis: Redis,
    *,
    include_login_times: bool,
    query: str | None = None,
) -> PeopleList:
    """Everyone who can be messaged or mentioned, with live presence.

    Deactivated accounts are excluded: they cannot sign in, so offering them as a chat
    contact would only produce messages nobody will ever read.
    """
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.display_name, User.email)
    if query:
        pattern = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            User.email.ilike(pattern)
            | User.display_name.ilike(pattern)
            | User.first_name.ilike(pattern)
            | User.last_name.ilike(pattern)
        )
    users = list((await db.execute(stmt)).scalars().all())
    ids = [user.id for user in users]

    roles = await _roles_by_user(db, ids)
    avatars = await _has_avatar(db, ids)
    live = await presence_service.statuses(redis, ids)

    people: list[PersonOut] = []
    online = 0
    for user in users:
        state = presence_service.classify(live.get(user.id, False), user.last_seen_at)
        if state == "online":
            online += 1
        people.append(
            PersonOut(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                first_name=user.first_name,
                last_name=user.last_name,
                job_title=user.job_title,
                roles=roles.get(user.id, []),
                has_avatar=user.id in avatars,
                status=state,
                last_seen_at=user.last_seen_at,
                last_login_at=user.last_login_at if include_login_times else None,
            )
        )
    return PeopleList(people=people, online=online)

"""Live presence: who is online right now, and when everyone else was last seen.

Presence is kept in Redis, not Postgres. Every authenticated request refreshes a key that
expires on its own, so "online" is a fact about the last two minutes rather than a flag
somebody has to remember to clear - a crashed tab, a closed laptop or a killed container
all resolve correctly by simply letting the key lapse.

The durable columns (``last_seen_at``, ``last_login_at``) still live on ``users``, but the
seen timestamp is written at most once every ``DB_WRITE_INTERVAL`` seconds. Without that
throttle every API call would issue an UPDATE against the users row, turning a read-heavy
dashboard into a write-heavy one for no benefit.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User

logger = logging.getLogger("app.presence")

Status = Literal["online", "away", "offline"]

# A heartbeat is refreshed on every request; this is how long one counts for.
ONLINE_TTL_SECONDS = 120
# Seen within this window but no longer holding a heartbeat: idle rather than gone.
AWAY_AFTER = timedelta(minutes=15)
# Cap on how often the heartbeat is persisted to Postgres.
DB_WRITE_INTERVAL = timedelta(minutes=5)

_PRESENCE_KEY = "presence:{user_id}"
_DB_WRITE_KEY = "presence-db:{user_id}"


def _key(user_id: UUID) -> str:
    return _PRESENCE_KEY.format(user_id=user_id)


async def touch(
    redis: Redis,
    db: AsyncSession,
    user_id: UUID,
    *,
    login_at: datetime | None = None,
) -> None:
    """Record that ``user_id`` is active right now.

    Called on every authenticated request, so it must stay cheap: one Redis SET in the
    common case. Presence is a nicety - if Redis is unavailable the request must still
    succeed, so failures are logged and swallowed rather than raised.

    ``login_at`` is the token's authentication time. It is stored as ``last_login_at`` only
    when it moves forward, so re-authenticating updates it but a stale cached token cannot
    drag it backwards.
    """
    now = datetime.now(UTC)
    try:
        await redis.set(_key(user_id), now.isoformat(), ex=ONLINE_TTL_SECONDS)
        # NX + TTL as a rate limiter: the key only sets when absent, and while it exists we
        # skip the database entirely.
        should_write = await redis.set(
            _DB_WRITE_KEY.format(user_id=user_id),
            "1",
            ex=int(DB_WRITE_INTERVAL.total_seconds()),
            nx=True,
        )
    except Exception:  # noqa: BLE001 - presence must never break a request
        logger.warning("presence: redis unavailable, skipping heartbeat", exc_info=True)
        return

    if not should_write and login_at is None:
        return

    values: dict[str, datetime] = {"last_seen_at": now}
    if login_at is not None:
        values["last_login_at"] = login_at

    try:
        stmt = update(User).where(User.id == user_id).values(**values)
        if login_at is not None:
            # Only move the login stamp forward.
            stmt = stmt.where((User.last_login_at.is_(None)) | (User.last_login_at < login_at))
        await db.execute(stmt)
        await db.commit()
    except Exception:  # noqa: BLE001 - same reasoning as above
        await db.rollback()
        logger.warning("presence: could not persist last_seen_at", exc_info=True)


async def statuses(redis: Redis, user_ids: list[UUID]) -> dict[UUID, bool]:
    """Which of these users hold a live heartbeat. One pipeline, not N round trips."""
    if not user_ids:
        return {}
    try:
        pipe = redis.pipeline()
        for user_id in user_ids:
            pipe.exists(_key(user_id))
        results = await pipe.execute()
    except Exception:  # noqa: BLE001
        logger.warning("presence: redis unavailable, everyone reads as offline", exc_info=True)
        return dict.fromkeys(user_ids, False)
    return {user_id: bool(result) for user_id, result in zip(user_ids, results, strict=True)}


def classify(is_live: bool, last_seen: datetime | None) -> Status:
    """online = heartbeat now; away = seen recently but idle; offline = neither.

    Mirrors what a chat client shows, and never claims "online" from a timestamp alone -
    only a live heartbeat earns that.
    """
    if is_live:
        return "online"
    if last_seen is not None and datetime.now(UTC) - last_seen <= AWAY_AFTER:
        return "away"
    return "offline"

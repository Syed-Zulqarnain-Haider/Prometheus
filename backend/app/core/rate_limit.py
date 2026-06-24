"""Per-user sliding-window rate limiting backed by Redis.

A sorted set per user holds one entry per request, scored by timestamp. On each
request we drop entries older than the window, count what remains, and reject with
429 + Retry-After if the limit is reached. Defaults: 300 requests / 60s (general),
10 / 60s (export).
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis

from app.api.deps import CurrentUser, VerifiedUser
from app.core.redis import get_redis

RATE_LIMIT = 300
EXPORT_RATE_LIMIT = 10
SYNC_RATE_LIMIT = 3
ACCESS_REQUEST_RATE_LIMIT = 5
WINDOW_SECONDS = 60


async def _enforce(redis: Redis, key: str, limit: int) -> None:
    now = time.time()
    await redis.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
    count = await redis.zcard(key)
    if count >= limit:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            oldest_score = float(oldest[0][1])
            retry_after = max(1, int(WINDOW_SECONDS - (now - oldest_score)) + 1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    await redis.zadd(key, {f"{now:.6f}-{uuid.uuid4().hex}": now})
    await redis.expire(key, WINDOW_SECONDS)


async def enforce_rate_limit(
    context: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Reject the request with 429 if the caller exceeded their general budget."""
    await _enforce(redis, f"rl:{context.user_id}", RATE_LIMIT)


async def enforce_export_rate_limit(
    context: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Tighter limit for the export endpoint (10/min)."""
    await _enforce(redis, f"rl:export:{context.user_id}", EXPORT_RATE_LIMIT)


async def enforce_sync_rate_limit(
    context: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Very tight limit for the on-demand sync trigger (3/min) to prevent abuse."""
    await _enforce(redis, f"rl:sync:{context.user_id}", SYNC_RATE_LIMIT)


async def enforce_access_request_rate_limit(
    identity: VerifiedUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Limit access-request submissions per (authenticated-but-unprovisioned) identity."""
    await _enforce(redis, f"rl:access:{identity.firebase_uid}", ACCESS_REQUEST_RATE_LIMIT)

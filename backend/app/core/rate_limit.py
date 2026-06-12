"""Per-user sliding-window rate limiting backed by Redis.

A sorted set per user holds one entry per request, scored by timestamp. On each
request we drop entries older than the window, count what remains, and reject with
429 + Retry-After if the limit is reached. Default: 120 requests / 60s (general).
"""

from __future__ import annotations

import time
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis

from app.api.deps import CurrentUser
from app.core.redis import get_redis

RATE_LIMIT = 120
WINDOW_SECONDS = 60


async def enforce_rate_limit(
    context: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Reject the request with 429 if the caller exceeded their request budget."""
    key = f"rl:{context.user_id}"
    now = time.time()

    await redis.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
    count = await redis.zcard(key)
    if count >= RATE_LIMIT:
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

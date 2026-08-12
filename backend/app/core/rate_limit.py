"""Per-user sliding-window rate limiting backed by Redis.

A sorted set per user holds one entry per request, scored by timestamp. On each
request we drop entries older than the window, count what remains, and reject with
429 + Retry-After if the limit is reached. Defaults: 300 requests / 60s (general),
10 / 60s (export).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import Response

from app.api.deps import CurrentUser, VerifiedUser
from app.core.http import client_ip
from app.core.redis import get_redis

RATE_LIMIT = 300
EXPORT_RATE_LIMIT = 10
SYNC_RATE_LIMIT = 3
ACCESS_REQUEST_RATE_LIMIT = 5
WINDOW_SECONDS = 60
# Pre-auth ceiling, keyed on the source address. Every other limiter in this module is
# keyed on an identity, so it only engages AFTER a token has been verified - which left
# unauthenticated traffic (each request costing a full RSA signature verification)
# entirely unbounded. Set well above what a real user's tab produces so a person behind
# a shared NAT is never the one who trips it.
PRE_AUTH_RATE_LIMIT = 600


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


async def enforce_pre_auth_rate_limit(request: Request, redis: Redis) -> None:
    """Cap requests per source address BEFORE authentication is attempted.

    Called from middleware rather than as a route dependency, because a route
    dependency would run after ``CurrentUser`` has already paid for token
    verification - which is the cost this exists to bound.
    """
    source = client_ip(request) or "unknown"
    await _enforce(redis, f"rl:ip:{source}", PRE_AUTH_RATE_LIMIT)


async def pre_auth_rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Apply the pre-auth ceiling to API traffic, and fail OPEN if Redis is down.

    A cache outage must not take the dashboard with it: the limiter is a safety valve,
    not an authorization control, and everything behind it still authenticates.
    """
    if request.url.path.startswith("/api/"):
        try:
            await enforce_pre_auth_rate_limit(request, get_redis())
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {"code": "rate_limited", "message": str(exc.detail)}},
                headers=exc.headers,
            )
        except RedisError:
            pass
    return await call_next(request)


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

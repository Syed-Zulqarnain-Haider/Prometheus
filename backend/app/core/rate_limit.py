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
SYNC_RATE_LIMIT = 6
# The "ask your data" assistant. Each question fans out into several model calls +
# scoped queries, so it gets its own tighter bucket (separate from the general budget)
# to bound both cost and load.
CHAT_RATE_LIMIT = 20
# Read-only / idempotent BigQuery admin actions (Test Connection, schema diff, schema
# match). Kept on their OWN bucket so they can't starve the heavy sync trigger's budget.
DIAGNOSTICS_RATE_LIMIT = 20
ACCESS_REQUEST_RATE_LIMIT = 5
WINDOW_SECONDS = 60


# Atomic sliding-window check-and-add. Doing prune → count → (gate) → add as separate
# round-trips let two concurrent requests both read count<limit before either added, so a
# caller could exceed the window. This Lua script runs the whole decision atomically on
# Redis. Returns {allowed(1|0), oldest_score} — oldest is used to compute Retry-After.
_ENFORCE_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, oldest[2] or '0'}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window)
return {1, '0'}
"""


async def _enforce(redis: Redis, key: str, limit: int) -> None:
    now = time.time()
    member = f"{now:.6f}-{uuid.uuid4().hex}"
    res = await redis.eval(_ENFORCE_LUA, 1, key, now, WINDOW_SECONDS, limit, member)
    allowed = int(res[0])
    if not allowed:
        raw = res[1]
        oldest_score = float(raw.decode() if isinstance(raw, bytes) else raw)
        retry_after = WINDOW_SECONDS
        if oldest_score > 0:
            retry_after = max(1, int(WINDOW_SECONDS - (now - oldest_score)) + 1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


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
    """Tight limit for the heavy on-demand sync trigger (and Clear Data) to prevent abuse.
    Its own bucket — read-only diagnostics use ``enforce_diagnostics_rate_limit`` so they
    can't consume this budget."""
    await _enforce(redis, f"rl:sync:{context.user_id}", SYNC_RATE_LIMIT)


async def enforce_diagnostics_rate_limit(
    context: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Limit for read-only / idempotent BigQuery admin actions (Test Connection, schema
    diff, schema match). Separate from the sync-trigger budget so running diagnostics
    never blocks the actual sync."""
    await _enforce(redis, f"rl:diag:{context.user_id}", DIAGNOSTICS_RATE_LIMIT)


async def enforce_chat_rate_limit(
    context: CurrentUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Tight limit for the ask-your-data assistant (20/min) — one question triggers several
    model calls + queries, so it gets its own bucket separate from the general budget."""
    await _enforce(redis, f"rl:chat:{context.user_id}", CHAT_RATE_LIMIT)


async def enforce_access_request_rate_limit(
    identity: VerifiedUser,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Limit access-request submissions per (authenticated-but-unprovisioned) identity."""
    await _enforce(redis, f"rl:access:{identity.firebase_uid}", ACCESS_REQUEST_RATE_LIMIT)

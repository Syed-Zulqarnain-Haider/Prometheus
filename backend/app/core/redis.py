"""Redis client for caching (resolved user contexts, aggregates, rate limits)."""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import get_settings

_settings = get_settings()

# decode_responses=True so values come back as str (we store JSON strings).
redis_client: redis.Redis = redis.from_url(_settings.redis_url, decode_responses=True)


def get_redis() -> redis.Redis:
    """FastAPI dependency returning the shared async Redis client."""
    return redis_client

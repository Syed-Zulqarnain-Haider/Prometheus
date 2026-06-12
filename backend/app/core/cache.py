"""Redis caching for aggregate query results.

Cache key = ``agg:<sha256(route + resolved_scope + params)>``. Two callers with
the same effective scope and params share a cache entry. TTL is 12h; the daily
sync job busts the ``agg:*`` namespace after each successful load.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from redis.asyncio import Redis

from app.schemas.auth import ScopeOut

AGG_PREFIX = "agg:"
AGG_TTL_SECONDS = 12 * 60 * 60  # 12h


def scope_token(scopes: Sequence[ScopeOut]) -> str:
    """Stable string identifying a caller's effective row scope."""
    return json.dumps(
        sorted((s.scope_type, s.scope_value or "") for s in scopes),
        separators=(",", ":"),
    )


def aggregate_cache_key(route: str, scope: str, params: dict[str, Any]) -> str:
    payload = json.dumps(
        {"route": route, "scope": scope, "params": params},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{AGG_PREFIX}{digest}"


async def cached_json(redis: Redis, key: str, producer: Callable[[], Awaitable[Any]]) -> Any:
    """Return cached JSON if present, else run ``producer``, cache, and return it."""
    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)
    value = await producer()
    await redis.set(key, json.dumps(value, default=str), ex=AGG_TTL_SECONDS)
    return value

"""Redis caching for aggregate query results.

Cache key = ``agg:<sha256(version + route + resolved_scope + perms + params)>``. Two
callers share an entry only when their effective row-scope AND permitted metric groups
match — so a cached payload (which contains only the producer's permitted measures) is
never served to a caller with different permissions. The daily sync busts the ``agg:*``
namespace after each successful load; TTL is a backstop aligned to that daily rebuild.

Note: this is the AGGREGATE cache. The per-user RBAC/context cache (``userctx:*`` in
``services.auth``) is separate and intentionally untouched here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis

from app.schemas.auth import ScopeOut

AGG_PREFIX = "agg:"

# Source data is rebuilt once daily (~05:16 UTC) and the sync busts ``agg:*`` on
# success, so a cached aggregate is valid until the next rebuild. Rather than a short
# fixed TTL (which forces repeated cold recomputes against a cold Neon free-tier DB
# throughout the day), we expire each entry shortly AFTER the next daily-rebuild
# boundary. An entry created at any time of day therefore survives until the next
# rebuild — at most one cold recompute per (scope, perms, params) per day.
REBUILD_HOUR_UTC = 5
REBUILD_MINUTE_UTC = 16
AGG_TTL_GRACE_SECONDS = 60 * 60  # live ~1h past the boundary (covers rebuild + bust)
AGG_TTL_MIN_SECONDS = 30 * 60  # floor, so an entry made right at the boundary is useful
AGG_TTL_MAX_SECONDS = 25 * 60 * 60  # safety cap (just over a day)

# Bump whenever the SHAPE of a cached aggregate response changes, so a deploy can
# never serve a stale-shaped payload from before the change (e.g. a summary cached
# before net_revenue_usd / gross_profit_usd / tech_cost_usd were added). The version
# is part of the cache key, so old entries are simply never read again.
SCHEMA_VERSION = "2"


def seconds_until_next_rebuild(now: datetime) -> int:
    """Seconds from ``now`` (UTC) to the next daily rebuild boundary."""
    boundary = now.replace(
        hour=REBUILD_HOUR_UTC, minute=REBUILD_MINUTE_UTC, second=0, microsecond=0
    )
    if boundary <= now:
        boundary += timedelta(days=1)
    return int((boundary - now).total_seconds())


def aggregate_ttl_seconds(now: datetime | None = None) -> int:
    """TTL for an aggregate entry: until just past the next daily rebuild boundary."""
    now = now or datetime.now(UTC)
    ttl = seconds_until_next_rebuild(now) + AGG_TTL_GRACE_SECONDS
    return max(AGG_TTL_MIN_SECONDS, min(ttl, AGG_TTL_MAX_SECONDS))


def scope_token(scopes: Sequence[ScopeOut]) -> str:
    """Stable string identifying a caller's effective row scope."""
    return json.dumps(
        sorted((s.scope_type, s.scope_value or "") for s in scopes),
        separators=(",", ":"),
    )


def perms_token(metric_groups: Iterable[str]) -> str:
    """Stable string identifying a caller's permitted metric groups.

    Part of the cache key so two callers who share a row-scope but NOT the same
    metric permissions never read each other's payloads (the payload only contains
    the producer's permitted measures). Defence in depth alongside query-builder RBAC.
    """
    return ",".join(sorted(set(metric_groups)))


def aggregate_cache_key(route: str, scope: str, perms: str, params: dict[str, Any]) -> str:
    payload = json.dumps(
        {"v": SCHEMA_VERSION, "route": route, "scope": scope, "perms": perms, "params": params},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{AGG_PREFIX}{digest}"


async def cached_json(
    redis: Redis,
    key: str,
    producer: Callable[[], Awaitable[Any]],
    *,
    ttl: int | None = None,
) -> Any:
    """Return cached JSON if present, else run ``producer``, cache, and return it."""
    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)
    value = await producer()
    await redis.set(key, json.dumps(value, default=str), ex=ttl or aggregate_ttl_seconds())
    return value

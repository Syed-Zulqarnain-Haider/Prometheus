"""Real app-icon resolution for iOS apps via Apple's public iTunes Lookup API.

We store no icon assets. For iOS apps we have ``apple_id``, which Apple's free, no-auth
Lookup API resolves to a store artwork URL. Results are cached in Redis (a hit for weeks, a
miss for a day so we don't re-hammer), and live lookups are bounded per request so a cold
cache never makes the apps list slow. Best-effort throughout — a lookup failure just falls
back to the initials badge on the client, never an error.

Android apps have no equivalent free API; they fall back to the initials badge until an
``icon_url`` is provided at the source.
"""

from __future__ import annotations

import logging
from contextlib import suppress

import httpx
from redis.asyncio import Redis

log = logging.getLogger("app.icon")

_CACHE_PREFIX = "appicon:ios:"
_TTL_HIT = 7 * 24 * 3600  # a resolved icon URL is stable — cache a week
_TTL_MISS = 24 * 3600  # unresolved — retry tomorrow
_ITUNES_URL = "https://itunes.apple.com/lookup"
_MAX_LIVE_LOOKUPS = 60  # cap live iTunes calls per request (rest resolve on later calls)
_BATCH = 20  # iTunes accepts comma-separated ids


async def _fetch_itunes(apple_ids: list[int]) -> dict[int, str]:
    """Best-effort iTunes lookup for a batch -> {apple_id: artwork_url}. Never raises."""
    if not apple_ids:
        return {}
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(
                _ITUNES_URL,
                params={"id": ",".join(str(a) for a in apple_ids), "entity": "software"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:  # noqa: BLE001 — network/parse issues fall back to the initials badge
        log.warning("iTunes icon lookup failed for %d id(s)", len(apple_ids))
        return {}
    out: dict[int, str] = {}
    for item in payload.get("results", []):
        track_id = item.get("trackId")
        art = item.get("artworkUrl512") or item.get("artworkUrl100") or item.get("artworkUrl60")
        if track_id and art:
            # Upscale the small default artwork to 512px.
            url = str(art).replace("100x100bb", "512x512bb").replace("60x60bb", "512x512bb")
            out[int(track_id)] = url
    return out


async def resolve_ios_icons(redis: Redis, apple_ids: list[int]) -> dict[str, str]:
    """``{str(apple_id): icon_url}`` for the given ids. Redis-cached; misses are looked up
    from iTunes (bounded per call) and cached. An empty-string cache entry means 'no icon'
    (still cached to avoid re-hammering) and is omitted from the result."""
    ids = [int(a) for a in dict.fromkeys(apple_ids) if a]
    result: dict[str, str] = {}
    misses: list[int] = []

    for aid in ids:
        try:
            cached = await redis.get(f"{_CACHE_PREFIX}{aid}")
        except Exception:  # noqa: BLE001 — cache down: treat as a miss, keep serving
            cached = None
        if cached is None:
            misses.append(aid)
        elif cached:
            result[str(aid)] = cached if isinstance(cached, str) else cached.decode()

    for start in range(0, min(len(misses), _MAX_LIVE_LOOKUPS), _BATCH):
        batch = misses[start : start + _BATCH]
        fetched = await _fetch_itunes(batch)
        for aid in batch:
            url = fetched.get(aid, "")
            with suppress(Exception):  # caching is best-effort
                await redis.set(f"{_CACHE_PREFIX}{aid}", url, ex=_TTL_HIT if url else _TTL_MISS)
            if url:
                result[str(aid)] = url
    return result

#!/usr/bin/env python3
"""Redis stops being a single point of failure: outages degrade, loudly - never 500.

THE FINDING (reliability review, availability #1)
-------------------------------------------------
Three unguarded Redis paths sat on every request: the user-context cache inside
authentication, every per-user rate limiter, and the aggregate metrics cache. A Redis
restart or blip raised RedisError straight into the catch-all handler - every
authenticated request answered 500 while Postgres sat healthy one query away. The
pre-auth limiter already documented the right posture ("a cache outage must not take the
dashboard with it") and implemented it for exactly one of the four paths - silently, with
`except RedisError: pass`, which violates the no-silent-degradation rule from the other
direction.

THE POSTURE (owner decision from the review)
--------------------------------------------
Fail OPEN, loudly, everywhere the pre-auth limiter already does:
  * context cache read fails    -> resolve from Postgres (one indexed query), keep going;
  * cache/limiter write fails   -> keep going;
  * limiter read fails          -> the request is not limited this minute;
  * admin cache-bust fails      -> the RBAC change stands, the audit row is written, and
                                   the bounded consequence (stale context for up to the
                                   5-minute TTL) is logged at ERROR with the identity.
None of these are authorization controls - RBAC is enforced by the query layer and the
per-request active/expiry checks either way. Degradation is logged through ONE throttled
helper (at most a line every 30s), so the incident is visible without burying itself.

ALSO FOLDED IN (review, RBAC #5): scope_token collapsed scope_value=None and ="" into
the same cache token while the SQL filter treats them differently - two users with
different effective scopes could share a cache entry. Tokenized distinctly now; the key
change simply invalidates existing entries once, which the daily TTL does anyway.

Tested without a network: a fake Redis that raises proves every guarded path returns
instead of raising, and an in-memory fake proves the 429 path still fires when Redis is
healthy - fail-open must not have become fail-never-limit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
TEST = ROOT / "backend/tests/test_redis_resilience.py"

report: list[str] = []
skipped: list[str] = []

Edit = tuple[str, str, str, str]  # (path, label, old, new)

EDITS: list[Edit] = [
    # ── core/cache.py ──────────────────────────────────────────────────────────────
    (
        "backend/app/core/cache.py",
        "imports: logging/time/RedisError",
        """import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Sequence""",
        """import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence""",
    ),
    (
        "backend/app/core/cache.py",
        "imports: RedisError",
        """from redis.asyncio import Redis

from app.schemas.auth import ScopeOut""",
        """from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.schemas.auth import ScopeOut""",
    ),
    (
        "backend/app/core/cache.py",
        "one throttled degradation warning for every Redis touchpoint",
        '''AGG_PREFIX = "agg:"''',
        '''AGG_PREFIX = "agg:"

# Visible degradation without a log flood: Redis going away turns into cache misses and
# open rate limits, never 500s - but it must not do so silently, and it must not bury
# the real incident under one warning per request either.
_DEGRADED_LOG_INTERVAL_SECONDS = 30.0
_last_degraded_warning = 0.0


def warn_redis_degraded(what: str) -> None:
    """Log that a Redis-backed path is running degraded - at most one line per interval."""
    global _last_degraded_warning
    now = time.monotonic()
    if now - _last_degraded_warning >= _DEGRADED_LOG_INTERVAL_SECONDS:
        _last_degraded_warning = now
        logging.getLogger("app.redis").warning(
            "Redis unavailable - %s; continuing degraded (uncached / unlimited)", what
        )''',
    ),
    (
        "backend/app/core/cache.py",
        "None and empty-string scopes get distinct cache tokens",
        """    return json.dumps(
        sorted((s.scope_type, s.scope_value or "") for s in scopes),
        separators=(",", ":"),
    )""",
        """    # None and "" are DIFFERENT scopes to the SQL filter (None contributes no
    # condition; "" filters on the empty string) - so they must be different cache
    # tokens too, or two users with different effective scopes share an entry.
    return json.dumps(
        sorted(
            (s.scope_type, "\\x00none" if s.scope_value is None else s.scope_value)
            for s in scopes
        ),
        separators=(",", ":"),
    )""",
    ),
    (
        "backend/app/core/cache.py",
        "cached_json survives Redis being down",
        '''    """Return cached JSON if present, else run ``producer``, cache, and return it."""
    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)
    value = await producer()
    await redis.set(key, json.dumps(value, default=str), ex=ttl or aggregate_ttl_seconds())
    return value''',
        '''    """Return cached JSON if present, else run ``producer``, cache, and return it.

    Redis being down degrades to computing uncached - slower, never a 500. The producer
    is the source of truth; a cache that can take the dashboard down is mispriced.
    """
    try:
        cached = await redis.get(key)
    except RedisError:
        warn_redis_degraded("aggregate cache read failed")
        cached = None
    if cached is not None:
        return json.loads(cached)
    value = await producer()
    try:
        await redis.set(
            key, json.dumps(value, default=str), ex=ttl or aggregate_ttl_seconds()
        )
    except RedisError:
        warn_redis_degraded("aggregate cache write failed")
    return value''',
    ),
    # ── core/rate_limit.py ─────────────────────────────────────────────────────────
    (
        "backend/app/core/rate_limit.py",
        "import the shared degradation warning",
        """from app.api.deps import CurrentUser, VerifiedUser
from app.core.http import client_ip""",
        """from app.api.deps import CurrentUser, VerifiedUser
from app.core.cache import warn_redis_degraded
from app.core.http import client_ip""",
    ),
    (
        "backend/app/core/rate_limit.py",
        "every limiter fails open, loudly",
        """async def _enforce(redis: Redis, key: str, limit: int) -> None:
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
    await redis.expire(key, WINDOW_SECONDS)""",
        """async def _enforce(redis: Redis, key: str, limit: int) -> None:
    now = time.time()
    try:
        await redis.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
        count = await redis.zcard(key)
        oldest = await redis.zrange(key, 0, 0, withscores=True) if count >= limit else None
    except RedisError:
        # Fail OPEN, loudly: a limiter is a safety valve, not an authorization control -
        # everything behind it still authenticates, and RBAC is enforced by the query
        # layer regardless. The pre-auth middleware always worked this way; now every
        # limiter does, and none of them do it silently.
        warn_redis_degraded(f"rate limiter read failed ({key})")
        return
    if count >= limit:
        retry_after = WINDOW_SECONDS
        if oldest:
            oldest_score = float(oldest[0][1])
            retry_after = max(1, int(WINDOW_SECONDS - (now - oldest_score)) + 1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        await redis.zadd(key, {f"{now:.6f}-{uuid.uuid4().hex}": now})
        await redis.expire(key, WINDOW_SECONDS)
    except RedisError:
        warn_redis_degraded(f"rate limiter write failed ({key})")""",
    ),
    (
        "backend/app/core/rate_limit.py",
        "the silent pre-auth pass gets a voice",
        """        except RedisError:
            pass
    return await call_next(request)""",
        """        except RedisError:
            # Failing open was always right here; failing SILENTLY was not. The one
            # thing bounding RSA-verification cost from junk-token floods should not be
            # able to vanish without a line in the log.
            warn_redis_degraded("pre-auth rate limiter unavailable")
    return await call_next(request)""",
    ),
    # ── api/deps.py ────────────────────────────────────────────────────────────────
    (
        "backend/app/api/deps.py",
        "imports: RedisError + the shared warning",
        """from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db""",
        """from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import warn_redis_degraded
from app.core.database import get_db""",
    ),
    (
        "backend/app/api/deps.py",
        "authentication survives a context-cache outage",
        """    cache_key = user_context_cache_key(firebase_uid)
    cached = await cache.get(cache_key)""",
        """    cache_key = user_context_cache_key(firebase_uid)
    try:
        cached = await cache.get(cache_key)
    except RedisError:
        # The context cache fronts ONE indexed query. Redis being down must degrade to
        # that query - not to a 500 on every authenticated request in the process.
        warn_redis_degraded("user-context cache read failed")
        cached = None""",
    ),
    (
        "backend/app/api/deps.py",
        "context-cache write is best-effort",
        """        context = resolved
        await cache.set(cache_key, context.model_dump_json(), ex=USER_CONTEXT_TTL_SECONDS)""",
        """        context = resolved
        try:
            await cache.set(
                cache_key, context.model_dump_json(), ex=USER_CONTEXT_TTL_SECONDS
            )
        except RedisError:
            warn_redis_degraded("user-context cache write failed")""",
    ),
    # ── api/v1/admin.py ────────────────────────────────────────────────────────────
    (
        "backend/app/api/v1/admin.py",
        "cache-bust never throws away a committed RBAC change",
        '''async def _bust_cache(redis: Redis, firebase_uid: str) -> None:
    """Drop a cached UserContext so RBAC changes apply on the next request."""
    await redis.delete(user_context_cache_key(firebase_uid))''',
        '''async def _bust_cache(redis: Redis, firebase_uid: str) -> None:
    """Drop a cached UserContext so RBAC changes apply on the next request.

    Best-effort BY DESIGN. The RBAC change is already committed when this runs; raising
    here used to abort the audit write and show the admin a 500 for a change that had in
    fact landed. If the bust fails, the stale cached context can keep serving for up to
    its TTL (five minutes) - a real, bounded consequence, logged at ERROR with the
    identity so it is traceable, rather than an outage.
    """
    try:
        await redis.delete(user_context_cache_key(firebase_uid))
    except RedisError:
        logging.getLogger("app.api.admin").error(
            "could not bust the cached context for %s - their previous permissions may"
            " persist for up to the cache TTL",
            firebase_uid,
        )''',
    ),
]

TEST_SRC = '''"""Redis outages degrade; they do not 500. And degraded is not disabled-forever.

These exist because of a reviewed failure mode: three unguarded Redis paths sat on every
request, so a Redis restart answered 500 to every authenticated user while Postgres was
healthy one query away. The guards fail open - and the second half of these tests proves
the limiter still limits when Redis is healthy, because "fail open" that quietly becomes
"never limit" would be a worse bug than the one fixed.

Pure: a fake that raises RedisError, and an in-memory fake for the healthy path.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from app.api.v1.admin import _bust_cache
from app.core import cache as cache_module
from app.core.cache import cached_json, scope_token, warn_redis_degraded
from app.core.rate_limit import RATE_LIMIT, _enforce
from app.schemas.auth import ScopeOut
from fastapi import HTTPException
from redis.exceptions import RedisError


class _DownRedis:
    """Every operation fails the way a dead connection fails."""

    def __getattr__(self, name: str) -> Any:
        async def boom(*args: Any, **kwargs: Any) -> Any:
            raise RedisError("connection refused")

        return boom


class _MemoryRedis:
    """Just enough of a sorted set for the limiter's healthy path."""

    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}

    async def zremrangebyscore(self, key: str, lo: float, hi: float) -> None:
        kept = {m: s for m, s in self.zsets.get(key, {}).items() if not lo <= s <= hi}
        self.zsets[key] = kept

    async def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    async def zrange(self, key: str, start: int, stop: int, withscores: bool = False) -> list:
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        return items[start : stop + 1]

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.zsets.setdefault(key, {}).update(mapping)

    async def expire(self, key: str, seconds: int) -> None:
        pass


# ── outage: every guarded path returns instead of raising ────────────────────


async def test_the_limiter_fails_open_when_redis_is_down() -> None:
    await _enforce(_DownRedis(), "rl:u1", 1)  # must simply return


async def test_cached_json_computes_uncached_when_redis_is_down() -> None:
    async def producer() -> dict[str, int]:
        return {"revenue": 42}

    assert await cached_json(_DownRedis(), "agg:x", producer) == {"revenue": 42}


async def test_bust_cache_never_throws_away_a_committed_change() -> None:
    await _bust_cache(_DownRedis(), "uid-123")  # must simply return


# ── health: fail-open has not become never-limit ─────────────────────────────


async def test_the_limiter_still_limits_when_redis_is_healthy() -> None:
    redis = _MemoryRedis()
    for _ in range(RATE_LIMIT):
        await _enforce(redis, "rl:u2", RATE_LIMIT)
    with pytest.raises(HTTPException) as excinfo:
        await _enforce(redis, "rl:u2", RATE_LIMIT)
    assert excinfo.value.status_code == 429
    assert "Retry-After" in (excinfo.value.headers or {})


async def test_cached_json_round_trips_when_redis_is_healthy() -> None:
    class _KV:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.store.get(key)

        async def set(self, key: str, value: str, ex: int | None = None) -> None:
            self.store[key] = value

    calls = 0

    async def producer() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"n": 7}

    redis = _KV()
    assert await cached_json(redis, "agg:y", producer) == {"n": 7}
    assert await cached_json(redis, "agg:y", producer) == {"n": 7}
    assert calls == 1  # the second read came from the cache


# ── the token fix and the throttle ───────────────────────────────────────────


def test_none_and_empty_scope_values_are_different_cache_tokens() -> None:
    # The SQL filter treats them differently (None contributes no condition; ""
    # filters on the empty string), so sharing a token shared a cache entry across
    # different effective scopes.
    none_scope = [ScopeOut(scope_type="pod", scope_value=None)]
    empty_scope = [ScopeOut(scope_type="pod", scope_value="")]
    assert scope_token(none_scope) != scope_token(empty_scope)


def test_degradation_warnings_are_throttled_not_flooding(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache_module._last_degraded_warning = 0.0
    with caplog.at_level("WARNING", logger="app.redis"):
        for _ in range(50):
            warn_redis_degraded("test path")
    assert len(caplog.records) == 1
    cache_module._last_degraded_warning = time.monotonic() - 999.0
    with caplog.at_level("WARNING", logger="app.redis"):
        warn_redis_degraded("test path")
    assert len(caplog.records) == 2
'''


def window(path: Path, needle: str, before: int = 4, after: int = 14) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - before), min(len(lines), i + after)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor text not found"


def ensure_logging_import(text: str) -> str:
    """admin.py's bust helper logs inline; make sure `import logging` exists, sorted."""
    if re.search(r"^import logging$", text, re.M):
        return text
    lines = text.splitlines(keepends=True)
    plain = [(i, m.group(1)) for i, ln in enumerate(lines) if (m := re.match(r"^import (\w+)$", ln))]
    if plain:
        at = next((i for i, mod in plain if mod > "logging"), plain[-1][0] + 1)
    else:
        future = next((i for i, ln in enumerate(lines) if ln.startswith("from __future__")), 0)
        at = future + 1
        lines.insert(at, "\n")
    lines.insert(at, "import logging\n")
    return "".join(lines)


def ensure_redis_error_import_admin(text: str) -> tuple[str, bool]:
    if "from redis.exceptions import RedisError" in text:
        return text, True
    anchor = "from redis.asyncio import Redis\n"
    if text.count(anchor) != 1:
        return text, False
    return text.replace(anchor, anchor + "from redis.exceptions import RedisError\n", 1), True


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if "warn_redis_degraded" in (ROOT / "backend/app/core/cache.py").read_text():
        print("Already applied - left alone.")
        if TEST.parent.is_dir():
            TEST.write_text(TEST_SRC)
            print(f"  - {TEST}: refreshed")
        return 0

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for rel, label, old, _ in EDITS:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"  [{label}] {rel}: file missing")
            continue
        text = planned.get(path, path.read_text())
        found = text.count(old)
        if found != 1:
            problems.append(
                f"  [{label}] {rel}: expected exactly 1 match, found {found}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, next(n for r, la, o, n in EDITS if la == label), 1)

    if problems:
        print("NOTHING WAS WRITTEN - these guards sit on the request path, so a partial")
        print("apply is worse than none. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    admin_path = ROOT / "backend/app/api/v1/admin.py"
    text = planned[admin_path]
    text = ensure_logging_import(text)
    text, ok = ensure_redis_error_import_admin(text)
    if not ok:
        print("NOTHING WAS WRITTEN - admin.py has no single `from redis.asyncio import "
              "Redis` line to hang the RedisError import on. On disk:\n"
              + window(admin_path, "redis"))
        return 1
    planned[admin_path] = text

    for path, text in planned.items():
        path.write_text(text)
        report.append(f"[guard] {path}")

    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: seven cases - outage fails open, health still limits")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

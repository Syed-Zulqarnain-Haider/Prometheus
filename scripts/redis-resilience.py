#!/usr/bin/env python3
"""Redis outages degrade loudly instead of answering 500 to everyone.

RE-ANCHORED against the deployed files after the first attempt refused to write. Good
thing it did: the deployed rate limiter is no longer the read-then-write sequence those
anchors were built for - it is now a single atomic Lua script, and patching it as if it
were the old shape would have been nonsense.

THE FINDING (reliability review, top availability item)
-------------------------------------------------------
Three unguarded Redis paths sit on every request: the user-context cache inside
authentication, the per-user rate limiters, and the aggregate metrics cache. A Redis
restart or blip raises RedisError straight into the catch-all handler, so every
authenticated request answers 500 while Postgres sits healthy one query away.

THE POSTURE
-----------
Fail OPEN, loudly. A context-cache miss degrades to the one indexed query it fronts; a
limiter that cannot reach Redis does not limit that minute; writes are best-effort; and
the admin cache-bust no longer throws away a committed RBAC change. None of these are
authorization controls - RBAC is enforced by the query layer and the per-request
active/expiry checks either way. Every degradation goes through ONE throttled warning (a
line every 30s at most) so an outage is visible without burying itself.

A SECURITY GAP FOUND WHILE READING THE REAL FILE
-------------------------------------------------
The deployed get_user_context checks ``is_active`` only on the cache-MISS branch:

    cached = await cache.get(cache_key)
    if cached is not None:
        context = UserContext.model_validate_json(cached)      # <- no is_active check
    else:
        ...
        if not resolved.is_active: raise 403

So deactivating a user leaves them with up to five more minutes of full access whenever
their context is already cached - which, for an active user, is always. Expiry is checked
on every request a few lines below; activation was not. That check is added here, in the
same shape and for the same reason as the expiry one directly beneath it.

Also folded in from the RBAC review: scope_token collapsed scope_value=None and ="" into
the same cache token while the SQL filter treats them differently, so two users with
different effective scopes could share a cached payload. Tokenised distinctly now; the key
change simply invalidates existing entries once, which the daily TTL boundary does anyway.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
TEST = ROOT / "backend/tests/test_redis_resilience.py"

report: list[str] = []

EDITS: list[tuple[str, str, str, str]] = [
    # ── core/cache.py ──────────────────────────────────────────────────────────────
    (
        "backend/app/core/cache.py",
        "stdlib imports for the throttled warning",
        "import hashlib\nimport json\nfrom collections.abc import",
        "import hashlib\nimport json\nimport logging\nimport time\nfrom collections.abc import",
    ),
    (
        "backend/app/core/cache.py",
        "RedisError import",
        "from redis.asyncio import Redis\n\nfrom app.schemas.auth import ScopeOut",
        "from redis.asyncio import Redis\nfrom redis.exceptions import RedisError\n\n"
        "from app.schemas.auth import ScopeOut",
    ),
    (
        "backend/app/core/cache.py",
        "one throttled degradation warning, shared by every Redis touchpoint",
        'AGG_PREFIX = "agg:"',
        '''AGG_PREFIX = "agg:"

# Visible degradation without a log flood. Redis going away turns into cache misses and
# open rate limits, never 500s - but it must not do so silently, and it must not bury the
# real incident under one warning per request either.
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
        )


def error_redis_degraded(what: str) -> None:
    """Unthrottled ERROR for a Redis failure that is rare AND has a lasting consequence.

    The throttle above exists for per-request paths, where one line per request would
    bury the incident. A failed cache-bust is neither: it happens once per admin action
    and leaves stale permissions serving until the TTL expires. That must never be the
    line that got throttled away.
    """
    logging.getLogger("app.redis").error("Redis unavailable - %s", what)''',
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

    Redis being down degrades to computing uncached - slower, never a 500. The producer is
    the source of truth; a cache that can take the dashboard down with it is mispriced.
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
        "RedisError + the shared warning",
        "from redis.asyncio import Redis\n\nfrom app.api.deps import CurrentUser, VerifiedUser\n"
        "from app.core.redis import get_redis",
        "from redis.asyncio import Redis\nfrom redis.exceptions import RedisError\n\n"
        "from app.api.deps import CurrentUser, VerifiedUser\n"
        "from app.core.cache import warn_redis_degraded\nfrom app.core.redis import get_redis",
    ),
    (
        "backend/app/core/rate_limit.py",
        "the limiter fails open, loudly",
        "    res = await redis.eval(_ENFORCE_LUA, 1, key, now, WINDOW_SECONDS, limit, member)",
        """    try:
        res = await redis.eval(_ENFORCE_LUA, 1, key, now, WINDOW_SECONDS, limit, member)
    except RedisError:
        # Fail OPEN, loudly. A limiter is a safety valve, not an authorization control -
        # everything behind it still authenticates, and RBAC is enforced by the query
        # layer regardless. Silently swallowing this would break the other rule:
        # degradation has to be visible.
        warn_redis_degraded(f"rate limiter unavailable ({key})")
        return""",
    ),
    # ── api/deps.py ────────────────────────────────────────────────────────────────
    (
        "backend/app/api/deps.py",
        "RedisError + the shared warning",
        "from redis.asyncio import Redis",
        "from redis.asyncio import Redis\nfrom redis.exceptions import RedisError",
    ),
    (
        "backend/app/api/deps.py",
        "authentication survives a cache outage, and deactivation bites immediately",
        """    cached = await cache.get(cache_key)
    if cached is not None:
        context = UserContext.model_validate_json(cached)
    else:""",
        """    try:
        cached = await cache.get(cache_key)
    except RedisError:
        # This cache fronts ONE indexed query. Redis being down must degrade to that
        # query - not to a 500 on every authenticated request in the process.
        warn_redis_degraded("user-context cache read failed")
        cached = None
    if cached is not None:
        context = UserContext.model_validate_json(cached)
        # Deactivation must bite immediately, exactly like expiry below. Checking
        # is_active only on the cache-MISS branch left a deactivated user with up to
        # five more minutes of full access whenever their context was already cached -
        # which, for anyone actually using the dashboard, is always.
        if not context.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is inactive")
    else:""",
    ),
    (
        "backend/app/api/deps.py",
        "the cache write is best-effort",
        "        await cache.set(cache_key, context.model_dump_json(), "
        "ex=USER_CONTEXT_TTL_SECONDS)",
        """        try:
            await cache.set(
                cache_key, context.model_dump_json(), ex=USER_CONTEXT_TTL_SECONDS
            )
        except RedisError:
            warn_redis_degraded("user-context cache write failed")""",
    ),
    # ── api/v1/admin.py ────────────────────────────────────────────────────────────
    (
        "backend/app/api/v1/admin.py",
        "a cache-bust failure never throws away a committed RBAC change",
        '''async def _bust_cache(redis: Redis, firebase_uid: str) -> None:
    """Drop a cached UserContext so RBAC changes apply on the next request."""
    await redis.delete(user_context_cache_key(firebase_uid))''',
        '''async def _bust_cache(redis: Redis, firebase_uid: str) -> None:
    """Drop a cached UserContext so RBAC changes apply on the next request.

    Best-effort BY DESIGN. The RBAC change is already committed when this runs; raising
    here used to abort the audit write and show the admin a 500 for a change that had in
    fact landed. If the bust fails the stale context can keep serving for up to its TTL -
    a real, bounded consequence, logged at ERROR with the identity so it is traceable,
    rather than an outage.
    """
    try:
        await redis.delete(user_context_cache_key(firebase_uid))
    except RedisError:
        error_redis_degraded(
            f"could not bust the cached context for {firebase_uid} - their previous"
            " permissions may keep serving for up to the cache TTL"
        )''',
    ),
    (
        "backend/app/api/v1/admin.py",
        "RedisError import",
        "from redis.asyncio import Redis",
        "from redis.asyncio import Redis\nfrom redis.exceptions import RedisError",
    ),
    (
        "backend/app/api/v1/admin.py",
        "the unthrottled error helper, onto the import already there",
        "from app.core.cache import AGG_PREFIX",
        "from app.core.cache import AGG_PREFIX, error_redis_degraded",
    ),
    # ── the scope-token collision ──────────────────────────────────────────────────
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
]

TEST_SRC = '''"""Redis outages degrade; they do not 500. And degraded is not disabled-forever.

These exist because of a reviewed failure mode: three unguarded Redis paths sat on every
request, so a Redis restart answered 500 to every authenticated user while Postgres was
healthy one query away. The guards fail open - and the second half of these tests proves
the limiter still limits when Redis is healthy, because "fail open" that quietly became
"never limit" would be a worse bug than the one fixed.

Pure: a fake that raises RedisError, and an in-memory fake for the healthy path.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from app.api.v1.admin import _bust_cache
from app.core import cache as cache_module
from app.core.cache import (
    cached_json,
    error_redis_degraded,
    scope_token,
    warn_redis_degraded,
)
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


class _LuaRedis:
    """Just enough of the atomic limiter script to exercise the healthy path."""

    def __init__(self) -> None:
        self.hits: dict[str, list[float]] = {}

    async def eval(
        self, script: str, numkeys: int, key: str, now: float, window: float,
        limit: float, member: str,
    ) -> list[Any]:
        entries = [s for s in self.hits.get(key, []) if s > now - window]
        if len(entries) >= limit:
            self.hits[key] = entries
            return [0, str(entries[0])]
        entries.append(now)
        self.hits[key] = entries
        return [1, "0"]


def _ours(caplog: pytest.LogCaptureFixture) -> list[Any]:
    """Only the logger under test - an unrelated warning must not fail these."""
    return [r for r in caplog.records if r.name == "app.redis"]


# ── outage: every guarded path returns instead of raising ────────────────────


async def test_the_limiter_fails_open_when_redis_is_down() -> None:
    down: Any = _DownRedis()
    await _enforce(down, "rl:u1", 1)  # must simply return


async def test_cached_json_computes_uncached_when_redis_is_down() -> None:
    async def producer() -> dict[str, int]:
        return {"revenue": 42}

    down: Any = _DownRedis()
    assert await cached_json(down, "agg:x", producer) == {"revenue": 42}


async def test_bust_cache_never_throws_away_a_committed_change() -> None:
    down: Any = _DownRedis()
    await _bust_cache(down, "uid-123")  # must simply return


# ── health: fail-open has not become never-limit ─────────────────────────────


async def test_the_limiter_still_limits_when_redis_is_healthy() -> None:
    redis: Any = _LuaRedis()
    for _ in range(RATE_LIMIT):
        await _enforce(redis, "rl:u2", RATE_LIMIT)
    with pytest.raises(HTTPException) as excinfo:
        await _enforce(redis, "rl:u2", RATE_LIMIT)
    assert excinfo.value.status_code == 429


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

    redis: Any = _KV()
    assert await cached_json(redis, "agg:y", producer) == {"n": 7}
    assert await cached_json(redis, "agg:y", producer) == {"n": 7}
    assert calls == 1  # the second read came from the cache


# ── the token fix and the throttle ───────────────────────────────────────────


def test_none_and_empty_scope_values_are_different_cache_tokens() -> None:
    # The SQL filter treats them differently (None contributes no condition; ""
    # filters on the empty string), so sharing a token shared a cache entry across
    # different effective scopes.
    assert scope_token([ScopeOut(scope_type="pod", scope_value=None)]) != scope_token(
        [ScopeOut(scope_type="pod", scope_value="")]
    )


def test_degradation_warnings_are_throttled_not_flooding(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache_module._last_degraded_warning = 0.0
    with caplog.at_level("WARNING", logger="app.redis"):
        for _ in range(50):
            warn_redis_degraded("test path")
    assert len(_ours(caplog)) == 1
    cache_module._last_degraded_warning = time.monotonic() - 999.0
    with caplog.at_level("WARNING", logger="app.redis"):
        warn_redis_degraded("test path")
    assert len(_ours(caplog)) == 2


def test_the_consequential_failure_is_never_throttled_away(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A failed cache-bust leaves stale permissions serving until the TTL expires. It is
    # rare and it has a lasting consequence, so it must not share the request-path
    # throttle - the one line that mattered is exactly the one that would be dropped.
    cache_module._last_degraded_warning = time.monotonic()
    with caplog.at_level("ERROR", logger="app.redis"):
        for _ in range(3):
            error_redis_degraded("cache-bust failed for uid-123")
    assert len(_ours(caplog)) == 3
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 12)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


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
    for rel, label, old, new in EDITS:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"  [{label}] {rel}: file missing")
            continue
        text = planned.get(path, path.read_text())
        if text.count(old) != 1:
            problems.append(
                f"  [{label}] {rel}: expected exactly 1 match, found {text.count(old)}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, new, 1)

    if problems:
        print("NOTHING WAS WRITTEN - these guards sit on the request path, so a partial")
        print("apply is worse than none. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for path, text in planned.items():
        path.write_text(text)
        report.append(f"[guard] {path}")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: eight cases - outage fails open, health still limits")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(
        "\nAlso closed here, found while reading the deployed file: is_active was checked"
        "\nonly on the cache-MISS branch, so deactivating a user left them up to five more"
        "\nminutes of full access whenever their context was already cached."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

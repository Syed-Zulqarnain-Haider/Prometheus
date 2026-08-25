#!/usr/bin/env python3
"""Drop every cached aggregate when App Master is edited.

WHY
    Live attribution makes an App Master edit move an app's whole history the
    moment it is saved - but only for a query that actually reaches Postgres.
    Every ``agg:*`` entry in Redis was computed under the OLD attribution and
    has a TTL running to the next daily rebuild boundary, so without this the
    dashboard keeps serving yesterday's grouping for up to a day and "instant"
    is a lie.

WHAT IT DOES
    Adds ``bust_aggregate_cache()`` to app.core.cache (the one implementation of
    a bust that already existed inline in integration_service), and calls it
    after the commit of every App Master mutation that writes a change through
    ``_write_change``.

WHY IT OPENS ITS OWN REDIS CLIENT
    ``update_row`` and its siblings take ``settings`` but no Redis handle, and
    threading one through would mean changing every caller including the request
    approval path. App Master edits are rare - a handful a day - so one
    short-lived connection per edit is the cheaper trade than a wider change
    surface. Stated plainly rather than hidden: this is a deliberate choice, not
    an oversight.

    The bust is best effort. An edit that has already committed to BigQuery and
    Postgres must never be reported as failed because Redis was unreachable; the
    worst case is the old TTL behaviour we have today.

SAFETY
    Nothing is written unless every edit resolves. Re-running is a no-op.
    Revert: git checkout -- backend/app/core/cache.py backend/app/services/app_master_service.py
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "backend" / "app" / "core" / "cache.py"
SERVICE = ROOT / "backend" / "app" / "services" / "app_master_service.py"
CONFIG = ROOT / "backend" / "app" / "core" / "config.py"
GUARD = ROOT / "backend" / "tests" / "test_app_master_cache_bust.py"

problems: list[str] = []
notes: list[str] = []

BUST_NAME = "bust_aggregate_cache"
MARKER = "_bust_aggregate_cache"


def fail(message: str) -> None:
    problems.append(message)


def note(message: str) -> None:
    notes.append(message)


def redis_setting() -> str:
    """The Settings attribute holding the Redis URL, read rather than assumed."""
    if not CONFIG.exists():
        fail("backend/app/core/config.py not found.")
        return "redis_url"
    match = re.search(r"^\s*(\w*redis\w*(?:_url)?)\s*:\s*str", CONFIG.read_text(encoding="utf-8"),
                      re.M | re.I)
    if match is None:
        fail("Could not find a Redis URL field on Settings - refusing to guess.")
        return "redis_url"
    note(f"Settings Redis field: {match.group(1)}")
    return match.group(1)


# ------------------------------------------------------------------ cache ---
BUST_HELPER = '''

async def {name}(redis: Redis) -> int:
    """Delete every cached aggregate. Returns how many entries were removed.

    Called whenever the numbers behind the cache change shape: after a successful
    daily sync, after analytics data is cleared, and after an App Master edit
    (which re-attributes an app's entire history and so invalidates every cached
    aggregate that grouped it under the old pod / hou / publisher).
    """
    removed = 0
    async for key in redis.scan_iter(f"{{AGG_PREFIX}}*", count=500):
        await redis.delete(key)
        removed += 1
    return removed
'''


def patch_cache() -> str | None:
    source = CACHE.read_text(encoding="utf-8")
    if f"async def {BUST_NAME}" in source:
        note("app/core/cache.py already defines bust_aggregate_cache - left as is.")
        return None
    return source.rstrip("\n") + "\n" + BUST_HELPER.format(name=BUST_NAME)


# ---------------------------------------------------------------- service ---
def service_helper(setting: str) -> str:
    return f'''

async def {MARKER}(settings: Settings) -> None:
    """Drop every cached aggregate after an App Master edit.

    Attribution (pod / pod_owner / hou / publisher) is resolved live from App
    Master at query time, so an edit changes the grouping of an app's ENTIRE
    history at once. Every ``agg:*`` entry was computed under the old grouping
    and would otherwise be served until the next daily rebuild boundary.

    Opens its own short-lived client: this call chain carries ``settings`` but no
    Redis handle, and App Master edits are rare enough that one connection per
    edit is cheaper than threading a handle through every caller.

    Best effort by design. The edit has already committed to BigQuery and
    Postgres by the time we get here; an unreachable Redis must not turn a
    successful edit into a failed request. The fallback is exactly today's
    behaviour - entries expire at the next rebuild boundary.
    """
    try:
        client = Redis.from_url(settings.{setting}, decode_responses=True)
        try:
            removed = await bust_aggregate_cache(client)
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001 - never fail an edit that already succeeded
        log.exception("aggregate cache bust after App Master edit failed (non-fatal)")
    else:
        log.info("App Master edit busted %s cached aggregate(s)", removed)
'''


def patch_service(setting: str) -> str | None:
    source = SERVICE.read_text(encoding="utf-8")
    if MARKER in source:
        note("app_master_service.py already busts the aggregate cache - left as is.")
        return None

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    # Every mutation that pushes a change through _write_change must bust, and it
    # must bust AFTER the commit - a bust before the commit races the very write
    # it is meant to invalidate.
    insertions: list[tuple[int, str]] = []
    targets: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == MARKER:
            continue
        calls = [
            n for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "_write_change"
        ]
        if not calls:
            continue
        if not isinstance(node, ast.AsyncFunctionDef):
            fail(f"{node.name}() writes changes but is not async - cannot await the bust.")
            continue
        if not any(a.arg == "settings" for a in node.args.args):
            fail(f"{node.name}() writes changes but has no `settings` argument.")
            continue
        commits = [
            n for n in ast.walk(node)
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Await)
            and isinstance(n.value.value, ast.Call)
            and isinstance(n.value.value.func, ast.Attribute)
            and n.value.value.func.attr == "commit"
        ]
        if not commits:
            fail(f"{node.name}() writes changes but never commits - not patching blind.")
            continue
        last = max(commits, key=lambda n: n.end_lineno or n.lineno)
        indent = " " * last.col_offset
        insertions.append((
            offsets[(last.end_lineno or last.lineno)],
            f"{indent}# Attribution changed for this app's whole history; every cached\n"
            f"{indent}# aggregate grouped it under the old values.\n"
            f"{indent}await {MARKER}(settings)\n",
        ))
        targets.append(f"{node.name}() after line {last.end_lineno}")

    if not insertions:
        fail("Found no App Master mutation to bust the cache after - refusing to write.")
        return None

    out = source
    for position, text in sorted(insertions, key=lambda item: -item[0]):
        out = out[:position] + text + out[position:]

    # imports
    if "from redis.asyncio import Redis" not in out:
        anchor = re.search(r"^from sqlalchemy[^\n]*$", out, re.M)
        if anchor is None:
            fail("app_master_service.py: no sqlalchemy import to anchor the Redis import to.")
            return None
        out = out[:anchor.start()] + "from redis.asyncio import Redis\n" + out[anchor.start():]

    if f"import {BUST_NAME}" not in out and f"{BUST_NAME}," not in out:
        existing = re.search(r"^from app\.core\.cache import ([^\n]+)$", out, re.M)
        if existing:
            out = out[:existing.start()] + f"from app.core.cache import {BUST_NAME}, " \
                + existing.group(1) + out[existing.end():]
        else:
            anchor = re.search(r"^from app\.[^\n]*$", out, re.M)
            if anchor is None:
                fail("app_master_service.py: no app.* import to anchor the cache import to.")
                return None
            out = out[:anchor.start()] + f"from app.core.cache import {BUST_NAME}\n" \
                + out[anchor.start():]

    # module logger
    if not re.search(r"^log(ger)?\s*=\s*logging\.getLogger", out, re.M):
        if not re.search(r"^import logging$", out, re.M):
            first = re.search(r"^import [^\n]*$", out, re.M)
            if first is None:
                fail("app_master_service.py: nowhere to add `import logging`.")
                return None
            out = out[:first.start()] + "import logging\n" + out[first.start():]
        last_import = None
        for match in re.finditer(r"^(?:import|from) [^\n]*$", out, re.M):
            last_import = match
        assert last_import is not None
        out = out[:last_import.end()] + "\n\nlog = logging.getLogger(__name__)" \
            + out[last_import.end():]
        note("added a module logger to app_master_service.py")
    logger_name = re.search(r"^(log(?:ger)?)\s*=\s*logging\.getLogger", out, re.M)
    if logger_name and logger_name.group(1) != "log":
        out = out.replace(f'log.exception("aggregate cache bust',
                          f'{logger_name.group(1)}.exception("aggregate cache bust')
        out = out.replace('log.info("App Master edit busted',
                          f'{logger_name.group(1)}.info("App Master edit busted')

    out = out.rstrip("\n") + "\n" + service_helper(setting)
    note(f"cache bust inserted after the commit in: {', '.join(targets)}")
    return out


# ------------------------------------------------------------------ guard ---
GUARD_SOURCE = '''"""An App Master edit must drop the cached aggregates it invalidated.

Attribution is resolved live from App Master, so an edit re-groups an app's whole
history. Any ``agg:*`` entry computed before the edit is wrong, not merely stale,
and would otherwise be served until the next daily rebuild boundary.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.cache import AGG_PREFIX, bust_aggregate_cache
from app.services import app_master_service


class _FakeRedis:
    """Just enough Redis to observe what a bust actually deletes."""

    def __init__(self, keys: dict[str, str]) -> None:
        self.keys = dict(keys)
        self.deleted: list[str] = []

    async def scan_iter(self, match: str, count: int = 500):  # noqa: ARG002
        prefix = match.rstrip("*")
        for key in list(self.keys):
            if key.startswith(prefix):
                yield key

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.keys.pop(key, None)


@pytest.mark.asyncio
async def test_bust_removes_aggregates_and_nothing_else() -> None:
    redis = _FakeRedis({
        f"{AGG_PREFIX}one": "x",
        f"{AGG_PREFIX}two": "x",
        "userctx:someone": "keep",
        "ratelimit:someone": "keep",
    })
    removed = await bust_aggregate_cache(redis)  # type: ignore[arg-type]
    assert removed == 2
    assert sorted(redis.deleted) == [f"{AGG_PREFIX}one", f"{AGG_PREFIX}two"]
    assert set(redis.keys) == {"userctx:someone", "ratelimit:someone"}


def _mutating_functions() -> list[ast.AsyncFunctionDef]:
    source = Path(inspect.getfile(app_master_service)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_write_change"
            for call in ast.walk(node)
        )
    ]


def test_every_app_master_mutation_busts_the_cache() -> None:
    """A new mutation added later must not silently skip the bust."""
    functions = _mutating_functions()
    assert functions, "found no App Master mutation - this guard has stopped checking"
    for node in functions:
        busts = [
            call
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_bust_aggregate_cache"
        ]
        assert busts, f"{node.name}() writes App Master but never busts the cache"


def test_the_bust_happens_after_the_commit() -> None:
    """Busting before the commit races the write it is meant to invalidate."""
    for node in _mutating_functions():
        commits = [
            n.lineno
            for n in ast.walk(node)
            if isinstance(n, ast.Await)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "commit"
        ]
        busts = [
            n.lineno
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_bust_aggregate_cache"
        ]
        assert commits and busts
        assert min(busts) > max(commits), (
            f"{node.name}() busts the cache at line {min(busts)}, "
            f"before its commit at line {max(commits)}"
        )
'''


# ------------------------------------------------------------------- main ---
def main() -> int:
    for path in (CACHE, SERVICE):
        if not path.exists():
            fail(f"missing: {path.relative_to(ROOT)}")
    if problems:
        report()
        return 1

    setting = redis_setting()
    cache_out = patch_cache()
    service_out = patch_service(setting)

    for label, text in (("cache.py", cache_out), ("app_master_service.py", service_out)):
        if text:
            try:
                ast.parse(text)
            except SyntaxError as exc:
                fail(f"{label}: patched source does not parse: {exc}")

    if problems:
        report()
        return 1

    if cache_out:
        CACHE.write_text(cache_out, encoding="utf-8")
    if service_out:
        SERVICE.write_text(service_out, encoding="utf-8")
    GUARD.write_text(GUARD_SOURCE, encoding="utf-8")
    note("wrote: test_app_master_cache_bust.py"
         + (", cache.py" if cache_out else "")
         + (", app_master_service.py" if service_out else ""))
    report()
    return 1 if problems else 0


def report() -> None:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED:")
        for line in problems:
            print(f"  - {line}")
    else:
        print("\nPATCHED. Verified only by the test suite: ./scripts/run-backend-tests.sh")


if __name__ == "__main__":
    raise SystemExit(main())

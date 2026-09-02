#!/usr/bin/env python3
"""Keyset pagination stops losing rows at NULLs, and bad input answers 400, not 500.

THE ROW-LOSS BUG (reliability review, RBAC/data-path #1 - the layer's one serious defect)
-----------------------------------------------------------------------------------------
Unmapped apps have NULL app_name / canonical_key BY DESIGN - the app_key COALESCE exists
because of them, and Data Health lists them. Keyset cursors compare with < and >, which
are UNKNOWN against NULL: sorting ascending by app name, every NULL-named row after the
last real page is silently dropped; descending, once the cursor passes the NULL block the
predicate is unknown for every remaining row and the ENTIRE rest of the table vanishes.
No error - the list just ends early. Apps Explorer is built on this query.

The fix orders and compares on NULL-free expressions: text NULLs become '' (a value no
real name uses), giving the NULL group a stable position and a stable tie-break identity,
and the cursor codec speaks the same sentinel on both sides - encode maps a NULL sort
value to '' (the position the SQL actually gave it) and decode maps a NULL key to ''.
Measure sorts are untouched: they are COALESCE(SUM(..), 0) and can never be NULL.

THE 400-vs-500 CLUSTER (findings #2-#4)
---------------------------------------
  * decode_cursor accepted any JSON value; a crafted or replayed cursor reached the bind
    layer and produced deterministic 500s. It now admits only the scalar shapes encode
    ever produces, and the query builder additionally rejects a cursor whose type does
    not match the sort column (a numeric cursor replayed against a text sort) - both as
    ValueError, which the routes already translate to 400.
  * /metrics/summary was the only route whose producer lacked the ValueError -> 400
    wrapper, so a user whose role grants zero metric groups got a 500 instead of a clean
    "no permitted metrics". Wrapped like its three siblings.
  * previous_period(0001-01-01) underflowed date.min with OverflowError, which nothing
    catches. It now raises ValueError and flows through the same wrappers.

Tested against the REAL query and codec: a seeded walk over a table containing a
NULL-named app and a NULL-keyed group, ascending and descending, asserting every row is
returned exactly once - the descending case is the one that silently lost the whole tail.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
TEST = ROOT / "backend/tests/test_table_pagination_nulls.py"

report: list[str] = []

Edit = tuple[str, str, str, str]

EDITS: list[Edit] = [
    (
        "backend/app/services/query_builder.py",
        "import String for the text-sort check",
        "from sqlalchemy import Select, and_, case, func, or_, select",
        "from sqlalchemy import Select, String, and_, case, func, or_, select",
    ),
    (
        "backend/app/services/query_builder.py",
        "previous_period cannot underflow into a 500",
        """        length = (params.date_to - params.date_from).days + 1
        prev_to = params.date_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=length - 1)
        return prev_from, prev_to""",
        """        length = (params.date_to - params.date_from).days + 1
        try:
            prev_to = params.date_from - timedelta(days=1)
            prev_from = prev_to - timedelta(days=length - 1)
        except OverflowError as exc:
            # date_from=0001-01-01 passes range validation but has no previous window.
            # ValueError rides the routes' existing 400 translation; OverflowError rode
            # nothing and surfaced as a 500.
            raise ValueError("date range has no previous period to compare against") from exc
        return prev_from, prev_to""",
    ),
    (
        "backend/app/services/query_builder.py",
        "NULL-safe keyset ordering + cursor/sort type agreement",
        """        sort_col = inner.c[sort]
        key_col = inner.c.canonical_key
        stmt = select(inner)

        if cursor is not None:
            last_sort, last_key = cursor""",
        """        # Annotated Any: both start as subquery columns and may be rebound to
        # COALESCE expressions below - mypy --strict rejects the rebind otherwise.
        sort_col: Any = inner.c[sort]
        key_col: Any = inner.c.canonical_key
        # NULLs are unordered by < and >, which silently DROPS rows once a keyset cursor
        # crosses them - and unmapped apps have NULL name/key BY DESIGN (the app_key
        # COALESCE exists because of them). Order and compare on NULL-free expressions:
        # text NULLs become '' (no real name), giving the NULL block a stable position
        # and a stable tie-break identity that the cursor codec shares. Measure sorts
        # are COALESCE(SUM(..), 0) and can never be NULL, so they pass through.
        text_sort = isinstance(sort_col.type, String)
        if text_sort:
            sort_col = func.coalesce(sort_col, "")
        key_col = func.coalesce(key_col, "")
        stmt = select(inner)

        if cursor is not None:
            last_sort, last_key = cursor
            # A cursor is opaque client state, but still input: a numeric cursor
            # replayed against a text sort (or vice versa) must be a 400 from the
            # route's ValueError translation, not an asyncpg bind error as a 500.
            if text_sort != isinstance(last_sort, str):
                raise ValueError("invalid cursor")""",
    ),
    (
        "backend/app/services/metrics_service.py",
        "encode speaks the same NULL sentinel the SQL orders by",
        '''def encode_cursor(sort_value: Any, key: str) -> str:
    raw = json.dumps([_to_jsonable(sort_value), key])
    return base64.urlsafe_b64encode(raw.encode()).decode()''',
        '''def encode_cursor(sort_value: Any, key: str) -> str:
    # The SQL orders on COALESCE(col, ''), so a NULL sort value's position IS '' -
    # encode that same sentinel, or the next page's comparison starts from a value
    # (null) the ordering never used and the walk goes wrong at exactly the NULL block.
    raw = json.dumps(["" if sort_value is None else _to_jsonable(sort_value), key])
    return base64.urlsafe_b64encode(raw.encode()).decode()''',
    ),
    (
        "backend/app/services/metrics_service.py",
        "decode admits only the shapes encode produces",
        '''def decode_cursor(token: str) -> tuple[Any, str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        value, key = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid cursor") from exc
    return value, str(key)''',
        '''def decode_cursor(token: str) -> tuple[Any, str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        value, key = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid cursor") from exc
    # Opaque is not trusted: only the scalar shapes encode ever writes come back in.
    # Anything else (a list, a dict, a bool, a null) used to reach the bind layer and
    # produce a deterministic 500 for whoever crafted - or merely mangled - a cursor.
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("invalid cursor")
    # A NULL canonical_key group's tie-break identity is '' - the same COALESCE the
    # SQL uses - never the string "None".
    return value, "" if key is None else str(key)''',
    ),
    (
        "backend/app/api/v1/metrics.py",
        "summary joins its siblings: ValueError is a 400",
        """    async def produce() -> dict[str, Any]:
        return await metrics_service.run_summary(db, qb, filters)""",
        """    async def produce() -> dict[str, Any]:
        try:
            return await metrics_service.run_summary(db, qb, filters)
        except ValueError as exc:
            # The only producer of the four without this wrapper - so a role with zero
            # metric groups (constructible in the admin panel) answered 500 here and
            # 400 everywhere else.
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc""",
    ),
]

TEST_SRC = '''"""Keyset pagination returns every row exactly once - including the NULL block.

Unmapped apps have NULL app_name / canonical_key by design, and keyset comparison
operators are unknown against NULL: before the fix, an ascending name walk dropped the
NULL-named rows and a DESCENDING walk lost the entire remainder of the table once the
cursor crossed the NULL block, with no error. These tests seed that exact pathology and
walk the real query both ways.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from app.core.fact_table import FACT_TABLE
from app.schemas.auth import ScopeOut, UserContext
from app.schemas.metrics import MetricFilters
from app.services.metrics_service import decode_cursor, encode_cursor, run_table
from app.services.query_builder import QueryBuilder
from sqlalchemy import insert

ALL_GROUPS = [
    "store_installs",
    "ua_spend",
    "ad_revenue",
    "iap_revenue",
    "attribution",
    "profitability",
]

WINDOW = MetricFilters(date_from=date(2026, 6, 1), date_to=date(2026, 6, 2))


def _admin() -> UserContext:
    return UserContext(
        user_id=uuid.uuid4(),
        firebase_uid="uid",
        email="u@terafort.org",
        display_name=None,
        is_active=True,
        roles=[],
        metric_groups=ALL_GROUPS,
        capabilities=[],
        scopes=[ScopeOut(scope_type="all", scope_value=None)],
    )


async def _seed(session: Any) -> None:
    """Two named apps, one NULL-NAMED app, and one NULL-KEYED group.

    The NULL-keyed rows carry no identity at all; the generated app_key falls back to
    'unknown', which is exactly how unmapped source rows land in production.
    """
    rows = [
        {"canonical_key": "appA", "app_name": "Alpha", "total_revenue_usd": 100},
        {"canonical_key": "appB", "app_name": "Beta", "total_revenue_usd": 200},
        {"canonical_key": "appC", "app_name": None, "total_revenue_usd": 300},
        {"canonical_key": None, "app_name": None, "total_revenue_usd": 400},
    ]
    for row in rows:
        await session.execute(
            insert(FACT_TABLE).values(date=date(2026, 6, 1), platform="ios", **row)
        )


async def _walk(session: Any, direction: str) -> list[Any]:
    """Every canonical_key the paginated table yields, across all pages of size 2."""
    qb = QueryBuilder(_admin())
    keys: list[Any] = []
    cursor: tuple[Any, str] | None = None
    for _ in range(10):  # a runaway loop is itself a failure
        page = await run_table(
            session, qb, WINDOW, sort="app_name", direction=direction, limit=2, cursor=cursor
        )
        keys += [row["canonical_key"] for row in page["rows"]]
        if page["next_cursor"] is None:
            return keys
        cursor = decode_cursor(page["next_cursor"])
    raise AssertionError("pagination never terminated")


async def test_an_ascending_walk_returns_the_null_block_too(fact_session: Any) -> None:
    await _seed(fact_session)
    keys = await _walk(fact_session, "asc")
    assert sorted(keys, key=lambda k: (k is None, k)) == ["appA", "appB", "appC", None]


async def test_a_descending_walk_does_not_lose_the_tail_after_the_null_block(
    fact_session: Any,
) -> None:
    # The severe case: descending, the cursor crosses the NULL block and every
    # remaining comparison used to be unknown - the rest of the table simply vanished.
    await _seed(fact_session)
    keys = await _walk(fact_session, "desc")
    assert len(keys) == 4
    assert sorted(keys, key=lambda k: (k is None, k)) == ["appA", "appB", "appC", None]


async def test_no_page_repeats_a_row(fact_session: Any) -> None:
    await _seed(fact_session)
    for direction in ("asc", "desc"):
        keys = await _walk(fact_session, direction)
        assert len(keys) == len({"<null>" if k is None else k for k in keys})


# ── the codec admits only what it writes ─────────────────────────────────────


def test_a_null_sort_value_encodes_as_the_sql_sentinel() -> None:
    value, key = decode_cursor(encode_cursor(None, "appC"))
    assert value == ""  # the position COALESCE(col, '') actually gave the row


def test_a_null_key_decodes_as_the_sql_sentinel_not_the_string_none() -> None:
    value, key = decode_cursor(encode_cursor("Alpha", None))
    assert key == ""


@pytest.mark.parametrize(
    "payload", ["W3sieCI6IDF9LCAiayJd", "W3RydWUsICJrIl0=", "W251bGwsICJrIl0="]
)
def test_a_crafted_cursor_is_a_value_error_not_a_bind_explosion(payload: str) -> None:
    # base64 of [{"x": 1}, "k"], [true, "k"], [null, "k"] - shapes encode never writes.
    with pytest.raises(ValueError):
        decode_cursor(payload)


def test_a_numeric_cursor_replayed_against_a_text_sort_is_refused() -> None:
    qb = QueryBuilder(_admin())
    with pytest.raises(ValueError, match="invalid cursor"):
        qb.table(WINDOW, sort="app_name", direction="asc", limit=2, cursor=(123.0, "k"))
    with pytest.raises(ValueError, match="invalid cursor"):
        qb.table(WINDOW, sort="total_revenue_usd", direction="asc", limit=2, cursor=("x", "k"))


def test_the_dawn_of_time_has_no_previous_period_and_says_so() -> None:
    filters = MetricFilters(date_from=date(1, 1, 1), date_to=date(1, 1, 5))
    with pytest.raises(ValueError, match="previous period"):
        QueryBuilder.previous_period(filters)
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 14)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if "text_sort" in (ROOT / "backend/app/services/query_builder.py").read_text():
        print("Already applied - left alone.")
        if TEST.parent.is_dir():
            TEST.write_text(TEST_SRC)
            print(f"  - {TEST}: refreshed")
        return 0

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for rel, label, old, new in EDITS:
        path = ROOT / rel
        text = planned.get(path, path.read_text()) if path.exists() else None
        if text is None:
            problems.append(f"  [{label}] {rel}: file missing")
            continue
        if text.count(old) != 1:
            problems.append(
                f"  [{label}] {rel}: expected exactly 1 match, found {text.count(old)}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, new, 1)

    if problems:
        print("NOTHING WAS WRITTEN - pagination correctness is all-or-nothing: the codec")
        print("and the SQL must speak the same sentinel or pages walk wrong. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    for path, text in planned.items():
        path.write_text(text)
        report.append(f"[fix] {path}")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: the NULL-block walks, the codec, and the 400s")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

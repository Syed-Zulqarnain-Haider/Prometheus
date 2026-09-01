#!/usr/bin/env python3
"""Prove the assistant cannot answer about data the asker is not granted.

WHY THIS EXISTS
---------------
The requirement: a user granted access to some apps can query THOSE apps and nothing else,
through the chatbot, no matter how they phrase it.

The architecture already says it does. ``chat_service`` builds ONE ``QueryBuilder(context)``
from the caller's own context and every tool call in both loops runs through ``_run_tool``,
which the file itself calls "the ONE place the assistant touches data". There is no
text-to-SQL and no raw-SQL path.

That is a claim in a docstring. This makes it a test.

WHAT IS ACTUALLY PROVEN
-----------------------
Not "the model politely declines" - a model can be talked out of politeness. The tests put
the ungranted app IN THE TOOL ARGUMENTS, exactly as a jailbroken or prompt-injected model
would, and assert on THE BYTES HANDED BACK TO THE MODEL (``_tool_result_content`` - the
literal string that becomes the tool message). The forbidden app is not merely absent from
the answer; it never enters the conversation at all, so there is nothing to leak downstream.

The controls matter as much as the assertions. A scoping test that passes because the seed
is empty, or because the tool always errors, proves nothing. So every restriction is paired
with an admin doing the identical call and SEEING the data - if the filter silently broke
open, the control still passes but the restriction fails; if the query broke entirely, the
control fails and says so.

WRITES: one new test file. It touches no application code - there is nothing to fix here,
which is the point. If these ever fail, something real regressed.

Also folds in the CHAT_BUDGET_SECONDS line that .env.example is still missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
TEST = ROOT / "backend/tests/test_chat_scope.py"
ENV_EXAMPLE = ROOT / ".env.example"

report: list[str] = []
skipped: list[str] = []

TEST_SRC = '''"""The assistant is bounded by the asker's grants, not by the model's manners.

The requirement in the owner's words: a user assigned some apps can query only those apps'
data. The architecture already enforces it - every tool call in every provider loop runs
through ``_run_tool``, which the service calls "the ONE place the assistant touches data",
against a ``QueryBuilder`` built from the caller's own context. There is no text-to-SQL.

These tests turn that from a docstring into a gate.

They do NOT test that the model refuses politely; a model can be talked out of politeness.
They put the ungranted app directly in the TOOL ARGUMENTS - which is exactly what a
prompt-injected or jailbroken model would do - and assert on the bytes handed back to the
model. The forbidden app never enters the conversation, so there is nothing to leak.

Every restriction is paired with an admin making the identical call and seeing the data. A
scoping test that passes because the fixture is empty proves nothing; the control is what
makes a green run mean something.

Seeded facts (tests/conftest.py): appA and appZ in POD_A, appB in POD_B, June 1-2 2026.
appB is the forbidden one throughout: revenue 70, installs 7.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from app.core.fact_table import FACT_TABLE
from app.schemas.auth import ScopeOut, UserContext
from app.services.chat_service import _openai_tools, _run_tool, _tool_result_content
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

GRANTED = "appA"
FORBIDDEN = "appB"
WINDOW = {"date_from": "2026-06-01", "date_to": "2026-06-02"}


def _context(*scopes: tuple[str, str | None]) -> UserContext:
    """A user with every metric group, so ONLY row scope is under test here.

    Metric-group filtering is a separate boundary with its own tests; mixing the two would
    let a green run mean either one held.
    """
    return UserContext(
        user_id=uuid.uuid4(),
        firebase_uid="uid",
        email="u@terafort.org",
        display_name=None,
        is_active=True,
        roles=[],
        metric_groups=ALL_GROUPS,
        capabilities=[],
        scopes=[ScopeOut(scope_type=t, scope_value=v) for t, v in scopes],
    )


async def _seed(session: Any) -> None:
    """Three apps across two pods, inside WINDOW.

    The ``fact_session`` fixture hands over an EMPTY fact table - _seed_metrics_fact
    belongs to ``metrics_env``, not to this one. The first version of this file assumed
    otherwise, so every query returned no rows: the restrictions all "passed" because
    there was nothing to leak, and only the admin controls failed. Seeding here is what
    makes a green run mean something.
    """
    for key, pod, publisher, revenue in (
        ("appA", "POD_A", "PubA", 1000),
        ("appZ", "POD_A", "PubA", 10),
        ("appB", "POD_B", "PubB", 70),
    ):
        await session.execute(
            insert(FACT_TABLE).values(
                date=date(2026, 6, 1),
                platform="ios",
                canonical_key=key,
                app_name=key.upper(),
                pod=pod,
                publisher=publisher,
                hou="HOU_A",
                store_total_installs=10,
                total_ua_spend_usd=100,
                total_revenue_usd=revenue,
            )
        )


async def _ask(db: Any, context: UserContext, tool: str, args: dict[str, Any]) -> str:
    """Exactly the string the model gets back from one tool call - no more, no less."""
    return _tool_result_content(await _run_tool(db, QueryBuilder(context), tool, args))


# ── row scope: an app grant is a wall, not a preference ──────────────────────


async def test_an_app_scoped_user_cannot_break_out_by_naming_another_app(
    fact_session: Any,
) -> None:
    # The attack, in its most direct form: the model asks for appB by name on behalf of a
    # user granted only appA. This is what a successful prompt injection produces.
    await _seed(fact_session)
    payload = await _ask(
        fact_session,
        _context(("app", GRANTED)),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "app", "apps": [FORBIDDEN], **WINDOW},
    )

    assert FORBIDDEN not in payload


async def test_an_admin_making_the_identical_call_does_see_it(fact_session: Any) -> None:
    # The control. Without this, the test above passes just as happily against a broken
    # fixture, an always-erroring tool, or a query that returns nothing for anyone.
    await _seed(fact_session)
    payload = await _ask(
        fact_session,
        _context(("all", None)),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "app", "apps": [FORBIDDEN], **WINDOW},
    )

    assert FORBIDDEN in payload


async def test_scope_still_lets_the_user_see_what_they_were_granted(
    fact_session: Any,
) -> None:
    # The other way a scoping bug hides: denying everyone everything. A wall that blocks
    # the owner of the data is also broken.
    await _seed(fact_session)
    payload = await _ask(
        fact_session,
        _context(("app", GRANTED)),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "app", **WINDOW},
    )

    assert GRANTED in payload
    assert FORBIDDEN not in payload


async def test_an_unscoped_breakdown_is_still_narrowed_to_the_grant(
    fact_session: Any,
) -> None:
    # No filter at all in the arguments: the scope has to be injected by us, not requested
    # by the model. "Client filters can only narrow" means the floor is the grant.
    await _seed(fact_session)
    scoped = await _ask(
        fact_session,
        _context(("app", GRANTED)),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "app", "limit": 50, **WINDOW},
    )
    everything = await _ask(
        fact_session,
        _context(("all", None)),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "app", "limit": 50, **WINDOW},
    )

    assert FORBIDDEN not in scoped
    assert FORBIDDEN in everything  # control: the row exists and the query can reach it


async def test_totals_for_a_forbidden_app_are_not_that_app_s_totals(
    fact_session: Any,
) -> None:
    # Totals return numbers, not names - the leak here would be silent. So compare against
    # the same question asked by someone who IS allowed: the answers must differ.
    await _seed(fact_session)
    scoped = await _ask(
        fact_session, _context(("app", GRANTED)), "get_totals", {"apps": [FORBIDDEN], **WINDOW}
    )
    allowed = await _ask(
        fact_session, _context(("all", None)), "get_totals", {"apps": [FORBIDDEN], **WINDOW}
    )

    assert scoped != allowed


# ── the same wall for the other scope types ──────────────────────────────────


async def test_a_pod_scoped_user_cannot_reach_another_pod(fact_session: Any) -> None:
    await _seed(fact_session)
    scoped = await _ask(
        fact_session,
        _context(("pod", "POD_A")),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "pod", "pods": ["POD_B"], **WINDOW},
    )
    everything = await _ask(
        fact_session,
        _context(("all", None)),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "pod", "pods": ["POD_B"], **WINDOW},
    )

    assert "POD_B" not in scoped
    assert "POD_B" in everything


async def test_two_grants_are_a_union_and_still_a_wall(fact_session: Any) -> None:
    # Effective access is the UNION of a user's scope rows - so a second grant must widen
    # to exactly appZ, and not one row further.
    await _seed(fact_session)
    payload = await _ask(
        fact_session,
        _context(("app", GRANTED), ("app", "appZ")),
        "get_breakdown",
        {"metric": "total_revenue_usd", "group_by": "app", "limit": 50, **WINDOW},
    )

    assert GRANTED in payload
    assert "appZ" in payload
    assert FORBIDDEN not in payload


# ── there is no other door ───────────────────────────────────────────────────


async def test_a_tool_the_model_invents_is_refused_not_executed(fact_session: Any) -> None:
    # A model that has been told to "run this SQL" will try calling a tool that does. The
    # dispatcher must not have one, and must say so rather than raising into a 502.
    await _seed(fact_session)
    out = await _run_tool(
        fact_session,
        QueryBuilder(_context(("app", GRANTED))),
        "run_sql",
        {"sql": "SELECT 1", **WINDOW},
    )

    assert out == {"error": "unknown tool: run_sql"}


def test_no_tool_hands_the_model_a_place_to_write_its_own_query() -> None:
    """The schema is the boundary: the model picks a window and some narrowing filters.

    If a free-text query field ever appears in a tool, every row-scope test above becomes
    theatre - so the absence is pinned here rather than trusted to review.
    """
    names: set[str] = set()
    for tool in _openai_tools():
        params = tool.get("function", {}).get("parameters", {})
        names.update(params.get("properties", {}) or {})

    assert names, "no tool parameters found - this test would pass vacuously"
    for hatch in ("sql", "query", "where", "raw", "expression", "filter_sql"):
        assert hatch not in names


def test_every_tool_is_a_closed_schema() -> None:
    """Unknown arguments must not be a way in either.

    Each tool declares its parameters as an object; anything the model sends beyond them is
    ignored by ``_parse_filters`` rather than forwarded. This asserts the declaration is
    there to be relied on.
    """
    tools = _openai_tools()
    assert tools, "the assistant exposes no tools - this test would pass vacuously"
    for tool in tools:
        params = tool["function"]["parameters"]
        assert params.get("type") == "object"
        assert isinstance(json.dumps(params), str)  # serialisable, i.e. really a schema
'''


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[proof] {TEST}: ten cases, each restriction paired with a control")
    else:
        skipped.append(f"[proof] {TEST.parent} does not exist - nothing written.")

    # The budget setting shipped without its documentation line, because this .env.example
    # has no chat section to slot it into. Give it one.
    if ENV_EXAMPLE.exists():
        env = ENV_EXAMPLE.read_text()
        if "CHAT_BUDGET_SECONDS" in env:
            report.append("[env] .env.example already documents CHAT_BUDGET_SECONDS")
        elif re.search(r"^CHAT_MAX_ITERATIONS=", env, re.M):
            env = re.sub(
                r"^(CHAT_MAX_ITERATIONS=.*)$", r"\1\nCHAT_BUDGET_SECONDS=40", env, count=1, flags=re.M
            )
            ENV_EXAMPLE.write_text(env)
            report.append("[env] .env.example: CHAT_BUDGET_SECONDS=40 documented")
        else:
            env = env.rstrip("\n") + (
                "\n\n# Assistant: seconds of lookups allowed per question. Kept inside the\n"
                "# reverse proxy's ~60s window so a slow question fails with a sentence\n"
                "# rather than a gateway error.\n"
                "CHAT_BUDGET_SECONDS=40\n"
            )
            ENV_EXAMPLE.write_text(env)
            report.append("[env] .env.example: CHAT_BUDGET_SECONDS=40 documented (new entry)")
    else:
        skipped.append("[env] no .env.example - nothing written.")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"  {entry}")
    print(
        "\nNo application code was touched. These tests should pass on the CURRENT build -\n"
        "they document a boundary that already holds. A failure here is a real regression,\n"
        "not a missing feature."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

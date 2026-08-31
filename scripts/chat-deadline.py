#!/usr/bin/env python3
"""The assistant gets a clock, so it fails on our terms instead of nginx's.

THE FAILURE
-----------
    POST /api/v1/chat -> 200 (108247.0ms)

That is a SUCCESS in the log. The user saw a bare nginx "Gateway Time-out". nginx hangs up
at ~60 seconds; the request ran 108, finished correctly, and wrote a good answer to a
socket the browser had abandoned 48 seconds earlier. Nobody was lying - we were measuring
different things.

Nothing in chat_service.py owned a clock. `grep timeout` over the file returned nothing.
`chat_max_iterations` caps HOW MANY provider round trips a question may take, never how
long they may take, and eight rounds at ~13 seconds each clears sixty comfortably.

THE FIX, AND WHY IT IS THIS ONE
-------------------------------
Not "raise the nginx timeout". That moves the cliff without adding a guardrail: the user
waits two minutes instead of one and still gets a gateway error at the end, and we still
learn nothing from it. A request that cannot be answered in time must fail INSIDE the
application, where it can say a sentence.

So the loop gets a wall-clock budget, deliberately smaller than nginx's window, and three
things follow from it:

  * every provider call is bounded by the time still left, so one hung round trip cannot
    eat the whole budget;
  * when the budget runs out mid-question the loop stops asking for tools and makes ONE
    last call to turn what it already gathered into an answer, with an instruction to say
    what it could not check - a partial honest answer beats a dropped connection;
  * if even that does not land, the user gets a plain sentence explaining what happened
    and how to ask a smaller question. Never an empty bubble, never a raw 504.

The same wrap-up path already existed for the iteration cap. This gives it a second
entrance and a reason to be honest about which one it came through.

Budget arithmetic: 40s of lookups + at most 12s of wrap-up = ~52s worst case, inside
nginx's 60. `CHAT_BUDGET_SECONDS` in the environment moves it without a rebuild.

SCOPE: this patches the OpenAI-compatible loop - the live path, and the one Gemini, OpenAI
and xAI all share. The Anthropic loop is NOT touched here: I can read it, but not the whole
of it, and half-anchoring a change into code I have only partly seen is how you turn one
bug into two. It gets the same treatment once I have read it end to end.

The script also PRINTS (writes nothing) the error handler in chat.py and the chat test
inventory, because the next two jobs - logging the correlation ref next to the exception,
and proving the row-scoping with a test - need those anchors.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
SERVICE = ROOT / "backend/app/services/chat_service.py"
TEST = ROOT / "backend/tests/test_chat_deadline.py"
ENV_EXAMPLE = ROOT / ".env.example"

report: list[str] = []
skipped: list[str] = []


# ── the pieces that go into chat_service.py ────────────────────────────────────────

HELPER = '''_WRAP_UP_SECONDS = 12.0

_OUT_OF_TIME = (
    "You are out of time for lookups. Answer now using ONLY the tool results already in "
    "this conversation. Say plainly which part you could not check, and suggest a narrower "
    "question - a shorter date range, fewer apps, or one metric at a time. Never state a "
    "number you did not retrieve."
)

_HIT_THE_CAP = (
    "You have used every lookup allowed for one question. Answer now from what you already "
    "retrieved, say what is missing, and suggest a narrower question."
)

_TOO_SLOW = (
    "That question took longer than I am allowed to spend on it, so I stopped rather than "
    "leave you waiting on a connection that was about to drop. Try it narrower - a shorter "
    "date range, fewer apps, or one metric at a time."
)


class _Deadline:
    """A wall clock for one question.

    The assistant sits behind nginx, which hangs up at sixty seconds. Before this existed a
    question needing several lookups ran 108 seconds, finished perfectly, and wrote its
    answer to a socket the browser had already given up on: the log recorded a 200, the user
    saw "Gateway Time-out". Failing on our own terms, inside the budget, is the whole
    difference between an honest sentence and a dead connection.
    """

    __slots__ = ("_end",)

    def __init__(self, seconds: float) -> None:
        # A floor of one second: a misconfigured 0 must not make every request fail
        # instantly, which would be a worse outage than the one this fixes.
        self._end = time.monotonic() + max(1.0, float(seconds))

    def remaining(self) -> float:
        return max(0.0, self._end - time.monotonic())

    def expired(self) -> bool:
        return self.remaining() <= 0.0


async def _within(deadline: _Deadline, call: Any) -> Any:
    """Run a provider call, but never past the deadline.

    Vendor-neutral on purpose: asyncio.wait_for behaves identically for the Anthropic client
    and the OpenAI-compatible one, so nothing here has to know which SDK raises what on a
    slow socket. On expiry the coroutine is cancelled rather than left running.
    """
    return await asyncio.wait_for(call, timeout=max(1.0, deadline.remaining()))


async def _final_answer(
    client: Any,
    model: str,
    max_tokens: int,
    convo: list[dict[str, Any]],
    nudge: str,
) -> str:
    """One last call, no tools, turning whatever we already have into an answer.

    Reached two ways - the model kept asking for tools until the iteration cap, or the
    question ran out of its time budget. Either way the user is owed a sentence, so this
    gets its own small budget on top of the main one; and if even that does not land, it
    says plainly what happened instead of returning an empty string.

    Takes ``max_tokens`` rather than the whole Settings object so it can be tested without
    constructing one.
    """
    convo = [*convo, {"role": "user", "content": nudge}]
    try:
        response = await _within(
            _Deadline(_WRAP_UP_SECONDS),
            client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=convo
            ),
        )
    except TimeoutError:
        return _TOO_SLOW
    return response.choices[0].message.content or _TOO_SLOW


'''

OLD_HEAD = '''    tool_calls = 0
    text = ""
    for _ in range(max(1, settings.chat_max_iterations)):
        response = await client.chat.completions.create(
            model=model,
            max_tokens=settings.chat_max_tokens,
            messages=convo,
            tools=tools,
            tool_choice="auto",
        )
'''

NEW_HEAD = '''    tool_calls = 0
    text = ""
    # nginx hangs up at ~60s. Budget the lookups well inside that, leaving room for the
    # wrap-up call, so the failure is ours to explain rather than the proxy's to dump.
    deadline = _Deadline(settings.chat_budget_seconds)
    wrap_up = ""
    for _ in range(max(1, settings.chat_max_iterations)):
        if deadline.expired():
            wrap_up = _OUT_OF_TIME
            break
        try:
            response = await _within(
                deadline,
                client.chat.completions.create(
                    model=model,
                    max_tokens=settings.chat_max_tokens,
                    messages=convo,
                    tools=tools,
                    tool_choice="auto",
                ),
            )
        except TimeoutError:
            # Nothing was appended, so the conversation is still balanced and the wrap-up
            # can answer from the tool results gathered on earlier rounds.
            wrap_up = _OUT_OF_TIME
            break
'''

OLD_TAIL = '''    else:
        response = await client.chat.completions.create(
            model=model, max_tokens=settings.chat_max_tokens, messages=convo
        )
        text = response.choices[0].message.content or ""
    return text, tool_calls
'''

NEW_TAIL = '''    else:
        wrap_up = _HIT_THE_CAP

    if wrap_up:
        text = await _final_answer(
            client, model, settings.chat_max_tokens, convo, wrap_up
        )
    return text, tool_calls
'''


# ── imports, kept in a shape ruff's isort already agrees with ──────────────────────

def ensure_plain_import(text: str, name: str) -> tuple[str, bool]:
    """Add `import <name>` in sorted position, or leave the file alone if it is there.

    Sorted position matters: ruff checks import order, and a correct patch that fails lint
    is a failed patch.
    """
    if re.search(rf"^import {re.escape(name)}$", text, re.M):
        return text, False
    lines = text.splitlines(keepends=True)
    plain = [(i, m.group(1)) for i, ln in enumerate(lines) if (m := re.match(r"^import (\w+)$", ln))]
    if plain:
        at = next((i for i, mod in plain if mod > name), plain[-1][0] + 1)
    else:
        future = next((i for i, ln in enumerate(lines) if ln.startswith("from __future__")), None)
        if future is None:
            return text, False
        at = future + 1
        lines.insert(at, "\n")
    lines.insert(at, f"import {name}\n")
    return "".join(lines), True


def window(path: Path, needles: tuple[str, ...], before: int = 3, after: int = 12) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    wanted: set[int] = set()
    for i, line in enumerate(lines):
        if any(n in line for n in needles):
            wanted.update(range(max(0, i - before), min(len(lines), i + after)))
    if not wanted:
        return f"      | {path}: none of {needles} appear"
    out, last = [f"      | {path}"], -2
    for i in sorted(wanted):
        if i != last + 1:
            out.append("      |     …")
        out.append(f"      | {i + 1:>4}  {lines[i]}")
        last = i
    return "\n".join(out)


# ── the setting ────────────────────────────────────────────────────────────────────

def patch_settings() -> None:
    hosts = [
        p
        for p in sorted((ROOT / "backend/app").rglob("*.py"))
        if "__pycache__" not in p.parts
        and re.search(r"^\s*chat_max_iterations\s*:", p.read_text(), re.M)
    ]
    if len(hosts) != 1:
        skipped.append(
            f"[setting] expected exactly one file declaring chat_max_iterations, found "
            f"{len(hosts)}: {[str(p) for p in hosts]}. Nothing written."
        )
        return
    path = hosts[0]
    text = path.read_text()
    if re.search(r"^\s*chat_budget_seconds\s*:", text, re.M):
        report.append(f"[setting] {path}: chat_budget_seconds already present - left alone")
        return
    match = re.search(r"^(?P<indent>\s*)chat_max_iterations\s*:.*$", text, re.M)
    assert match is not None
    indent = match.group("indent")
    line = (
        f"{indent}# Wall-clock budget for one question's lookups. Sits deliberately inside\n"
        f"{indent}# nginx's ~60s window: 40 here + at most 12 for the wrap-up call.\n"
        f"{indent}chat_budget_seconds: float = 40.0\n"
    )
    at = match.end() + 1
    path.write_text(text[:at] + line + text[at:])
    report.append(f"[setting] {path}: chat_budget_seconds = 40.0 (env CHAT_BUDGET_SECONDS)")

    if ENV_EXAMPLE.exists():
        env = ENV_EXAMPLE.read_text()
        if "CHAT_BUDGET_SECONDS" in env:
            report.append("[setting] .env.example already lists CHAT_BUDGET_SECONDS")
        elif "CHAT_MAX_ITERATIONS" in env:
            env = re.sub(
                r"^(CHAT_MAX_ITERATIONS=.*)$",
                r"\1\nCHAT_BUDGET_SECONDS=40",
                env,
                count=1,
                flags=re.M,
            )
            ENV_EXAMPLE.write_text(env)
            report.append("[setting] .env.example: CHAT_BUDGET_SECONDS=40 documented")


# ── the loop ───────────────────────────────────────────────────────────────────────

def patch_service() -> None:
    if not SERVICE.exists():
        skipped.append(f"[loop] missing {SERVICE} - nothing written.")
        return
    text = SERVICE.read_text()

    if "_Deadline" in text:
        report.append("[loop] already applied - left alone")
        return

    for label, block in (("head", OLD_HEAD), ("tail", OLD_TAIL)):
        if text.count(block) != 1:
            skipped.append(
                f"[loop] {SERVICE}: expected exactly one OpenAI-loop {label}, found "
                f"{text.count(block)}. NOTHING was written - a half-applied clock is worse\n"
                "  than no clock. On disk:\n"
                + window(SERVICE, ("chat_max_iterations", "chat.completions.create"))
            )
            return

    text = text.replace(OLD_HEAD, NEW_HEAD, 1)
    text = text.replace(OLD_TAIL, NEW_TAIL, 1)

    anchor = "async def _run_openai_loop("
    if text.count(anchor) != 1:
        skipped.append(f"[loop] {SERVICE}: no single `{anchor}` to sit above. Nothing written.")
        return
    at = text.index(anchor)
    text = text[:at] + HELPER + text[at:]

    for module in ("asyncio", "time"):
        text, added = ensure_plain_import(text, module)
        if added:
            report.append(f"[loop] {SERVICE}: added `import {module}`")

    SERVICE.write_text(text)
    report.append(
        f"[loop] {SERVICE}: the OpenAI-compatible loop now owns a clock - bounded provider "
        "calls, a graceful wrap-up on expiry, and an honest sentence if even that misses"
    )


TEST_SRC = '''"""The assistant answers inside its budget, or says so. It never just stops.

This exists because of a live incident: a question ran 108 seconds, the backend logged a
200, and the user got a bare nginx "Gateway Time-out" at sixty. The answer was fine - the
connection was gone. Nothing in the loop owned a clock.

Deliberately pure. No network, no provider key, no database: the unit under test is a
stopwatch and one wrap-up call.
"""

import asyncio
import time
from typing import Any

import pytest
from app.services import chat_service
from app.services.chat_service import _TOO_SLOW, _Deadline, _final_answer, _within

# ── the stopwatch ──────────────────────────────────────────────────────────────────

def test_a_fresh_deadline_has_its_budget_in_hand() -> None:
    deadline = _Deadline(40.0)
    assert not deadline.expired()
    assert 39.0 < deadline.remaining() <= 40.0


def test_an_elapsed_deadline_is_expired_and_never_reports_negative_time() -> None:
    deadline = _Deadline(1.0)
    deadline._end = time.monotonic() - 5.0  # five seconds past, without sleeping for it
    assert deadline.expired()
    assert deadline.remaining() == 0.0


def test_a_misconfigured_zero_budget_still_gets_a_second() -> None:
    # CHAT_BUDGET_SECONDS=0 in the environment must not make every question fail
    # instantly - that would be a worse outage than the one this guards against.
    assert _Deadline(0).remaining() > 0.5
    assert _Deadline(-99).remaining() > 0.5


# ── bounding one provider call ─────────────────────────────────────────────────────

async def test_a_quick_call_returns_its_value_untouched() -> None:
    async def quick() -> str:
        return "answered"

    assert await _within(_Deadline(30.0), quick()) == "answered"


async def test_a_call_that_outlives_the_deadline_is_cut_off() -> None:
    # The 108-second round trip, in miniature. Without this it runs to completion and
    # nginx decides the outcome instead of us.
    async def slow() -> str:
        await asyncio.sleep(30)
        return "too late"

    with pytest.raises(TimeoutError):
        await _within(_Deadline(0), slow())  # floors to 1s


# ── the wrap-up ────────────────────────────────────────────────────────────────────

class _Message:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str | None) -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str | None) -> None:
        self.choices = [_Choice(content)]


class _Completions:
    """Records what it was asked, so the test can assert on the payload, not just the reply."""

    def __init__(self, content: str | None, delay: float = 0.0) -> None:
        self.content = content
        self.delay = delay
        self.seen: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> _Response:
        self.seen = kwargs
        if self.delay:
            await asyncio.sleep(self.delay)
        return _Response(self.content)


class _Client:
    def __init__(self, content: str | None, delay: float = 0.0) -> None:
        self.completions = _Completions(content, delay)
        self.chat = self

    @property
    def seen(self) -> dict[str, Any]:
        return self.completions.seen


async def test_the_wrap_up_answers_from_what_was_already_gathered() -> None:
    client = _Client("Revenue was $137.8K, but I could not check ROAS.")
    convo: list[dict[str, Any]] = [{"role": "user", "content": "roas of top 3 apps"}]

    text = await _final_answer(client, "m", 500, convo, "out of time")

    assert text == "Revenue was $137.8K, but I could not check ROAS."
    # The nudge is appended, and the caller's conversation is not mutated behind its back.
    assert client.seen["messages"][-1] == {"role": "user", "content": "out of time"}
    assert len(convo) == 1


async def test_the_wrap_up_offers_no_tools() -> None:
    # It exists to force a text answer. Offering tools invites another round we have no
    # time left to run.
    client = _Client("done")
    await _final_answer(client, "m", 500, [], "out of time")
    assert "tools" not in client.seen
    assert "tool_choice" not in client.seen


async def test_an_empty_reply_becomes_an_explanation_not_a_blank_bubble() -> None:
    client = _Client(None)
    assert await _final_answer(client, "m", 500, [], "out of time") == _TOO_SLOW


async def test_a_wrap_up_that_hangs_still_ends_in_a_sentence() -> None:
    # The last line of defence: even the wrap-up can be slow, and the user still gets
    # words rather than a dropped connection.
    monkey = chat_service._WRAP_UP_SECONDS
    try:
        chat_service._WRAP_UP_SECONDS = 0.0  # floors to 1s inside _Deadline
        client = _Client("never arrives", delay=30)
        assert await _final_answer(client, "m", 500, [], "out of time") == _TOO_SLOW
    finally:
        chat_service._WRAP_UP_SECONDS = monkey


def test_the_honest_sentence_tells_the_user_what_to_do_next() -> None:
    # A timeout message that only says "timeout" teaches the user nothing.
    assert "narrower" in _TOO_SLOW
'''


def write_test() -> None:
    if not TEST.parent.is_dir():
        skipped.append(f"[test] {TEST.parent} does not exist - no test written.")
        return
    TEST.write_text(TEST_SRC)
    report.append(f"[test] {TEST}: ten cases pinning the clock and the wrap-up")


def recon() -> None:
    print("\n" + "=" * 78)
    print("READ-ONLY, for the next two jobs. Nothing below was modified.")
    print("=" * 78)
    print("\n--- the error handler, and where the ref does (not) get logged ---")
    print(window(ROOT / "backend/app/api/v1/chat.py", ("ref", "except", "unavailable", "logger")))
    print("\n--- existing chat tests (the scoping proof needs their fixtures) ---")
    for path in sorted((ROOT / "backend/tests").glob("*chat*")):
        print(f"      | {path}")
    print("\n--- how a scoped QueryBuilder is built for the assistant ---")
    print(window(ROOT / "backend/app/services/chat_service.py", ("QueryBuilder(",), before=6, after=8))


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    patch_settings()
    patch_service()
    write_test()

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")

    recon()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

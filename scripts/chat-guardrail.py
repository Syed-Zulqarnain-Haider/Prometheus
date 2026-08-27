#!/usr/bin/env python3
"""The assistant answers from your data, or it declines. Nothing in between.

Two failures look identical from the outside and are completely different underneath:

  * asked something off-topic, and it answers anyway;
  * asked a real data question, and it answers from the model's own memory instead of
    looking anything up.

The second is the dangerous one. The pipe is already safe - there is no SQL path, and the
two tools run through the caller's own scoped QueryBuilder - so a made-up number arrives
through a perfectly secure channel wearing the same confident tone as a real one. "It
cannot reach data it should not see" and "it looked at the data" are different promises,
and only the first one was being kept structurally.

HOW THIS IS ADDED WITHOUT REWRITING THE PROMPT
----------------------------------------------
The existing ``_system_prompt`` is renamed to ``_system_prompt_base`` and a new
``_system_prompt`` wraps it, appending the rules below. Nothing already in the prompt is
edited, reordered or re-indented - so whatever it says about tools, scopes and metric
names keeps saying it, and this cannot break by disagreeing with a sentence it never saw.
The wrapper forwards *args/**kwargs, so it does not depend on the signature either.

The rules themselves are deliberately about BEHAVIOUR, not about topics-as-keywords: a
list of banned subjects is a list somebody will find the edge of. "Answer only from a
lookup" has no edge - if there is no lookup, there is no answer.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
SERVICE = ROOT / "backend/app/services/chat_service.py"

DEF_RE = re.compile(r"^def _system_prompt\(", re.M)
CALL_RE = re.compile(r"\b_system_prompt\(")

GUARDRAIL = '''

# Appended to whatever the base prompt already says. Kept separate from it on purpose:
# these are rules about how to BEHAVE, and they must not be lost in a future edit to the
# prompt's description of the tools.
_GUARDRAIL = """

HARD RULES - these override anything above.

1. Never state a number, a name, a ranking or a date range that did not come back from a
   tool call in THIS conversation. You have no knowledge of this company's data. If you
   have not looked it up, you do not know it.

2. If a question is about this business - apps, revenue, spend, installs, profit, pods,
   owners, publishers, platforms, dates - call a tool. Do not answer it from memory, do
   not estimate, and do not describe what the answer would probably look like.

3. If a question is NOT about that data - general knowledge, coding, advice, chit-chat,
   anything about yourself - do not answer it. Reply with exactly:
   "I can only answer questions about your performance data - apps, revenue, spend,
   installs and profit. Ask me one of those and I will look it up."

4. If a tool returns nothing, say so plainly: no rows for that period or that filter.
   An empty result is an answer. Never fill the gap with a plausible figure.

5. If you cannot answer because the metric is outside what this person is allowed to see,
   say that. Do not substitute a metric they can see and present it as what was asked for.

6. Say which window and grouping the numbers came from, in one short line. A reader
   cannot tell a right answer from a wrong one unless they can see what was measured.
"""


def _system_prompt(*args: Any, **kwargs: Any) -> str:
    """The base prompt plus the behavioural guardrail.

    A wrapper rather than an edit: the base keeps sole responsibility for describing the
    tools and the caller's scope, and the rules below stay legible as a list of rules
    instead of being buried in the middle of it.
    """
    return _system_prompt_base(*args, **kwargs) + _GUARDRAIL
'''


def window(text: str, needle: str, before: int = 3, after: int = 10) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(
                f"      | {ln}" for ln in lines[max(0, i - before) : i + after]
            )
    return "      | (not found)"


def main() -> int:
    if not SERVICE.exists():
        print(f"ABORTED: missing {SERVICE}", file=sys.stderr)
        return 1

    text = SERVICE.read_text()
    if "_GUARDRAIL" in text:
        print("Already applied - left alone.")
        return 0

    defs = DEF_RE.findall(text)
    if len(defs) != 1:
        print(
            f"ABORTED - nothing was written.\n\nExpected exactly one top-level "
            f"`def _system_prompt(`, found {len(defs)}. On disk:\n"
            + window(text, "_system_prompt"),
            file=sys.stderr,
        )
        return 1

    # Rename the definition only; every CALL still says _system_prompt and now reaches
    # the wrapper. One rename, no call sites touched, no chance of missing one.
    text = DEF_RE.sub("def _system_prompt_base(", text, count=1)

    # The wrapper needs Any. Import it if the module does not already.
    if not re.search(r"^from typing import .*\bAny\b", text, re.M):
        typing_import = re.search(r"^from typing import (.+)$", text, re.M)
        if typing_import:
            names = sorted(
                {*[n.strip() for n in typing_import.group(1).split(",")], "Any"}
            )
            text = (
                text[: typing_import.start()]
                + f"from typing import {', '.join(names)}"
                + text[typing_import.end() :]
            )
        else:
            future = re.search(r"^from __future__ import annotations\n", text, re.M)
            insert_at = future.end() + 1 if future else 0
            text = text[:insert_at] + "from typing import Any\n" + text[insert_at:]

    # Place the wrapper immediately after the base function, so the two read together.
    base = re.search(r"^def _system_prompt_base\(", text, re.M)
    assert base is not None
    following = re.compile(r"^(?:async def |def |@|class )", re.M).search(
        text, base.end()
    )
    insert_at = following.start() if following else len(text)
    text = text[:insert_at].rstrip("\n") + "\n" + GUARDRAIL + "\n\n" + text[insert_at:]

    if len(CALL_RE.findall(text)) < 2:
        print(
            "ABORTED - nothing was written.\n\nAfter the rename there should be at least "
            "the wrapper's definition and its original call site referring to "
            "`_system_prompt`; there are fewer. Refusing to leave it half-renamed.",
            file=sys.stderr,
        )
        return 1

    SERVICE.write_text(text)
    print(
        "PATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    print("  - _system_prompt -> _system_prompt_base; a wrapper appends the guardrail")
    print(
        "  - never state a figure that did not come from a tool call in this conversation"
    )
    print("  - a data question must be looked up, never answered from memory")
    print("  - anything else gets one fixed sentence declining, not an answer")
    print(
        "  - empty result is reported as empty, not filled in with something plausible"
    )
    print("  - every answer says which window and grouping it measured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

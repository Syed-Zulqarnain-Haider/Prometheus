#!/usr/bin/env python3
"""The assistant echoes the model's turn back intact, instead of rebuilding it by hand.

THE FAILURE
-----------
Every question that needed a lookup came back "temporarily unavailable". The traceback:

    openai.BadRequestError: 400 - Function call is missing a thought_signature in
    functionCall parts. ... position 3

Gemini 3 attaches a THOUGHT SIGNATURE to every function call it returns and requires it
back in the conversation on the next turn. The loop rebuilt the assistant's turn from the
three fields it knew about - id, name, arguments - and silently dropped everything else,
including that signature. So the first call worked, the tool ran, and the SECOND round
trip was rejected. Position 3 is exactly the assistant's tool-call turn.

The key and the model were never the problem: Gemini answers HTTP 200 from inside the
container. This was our payload.

THE FIX, AND WHY IT IS THIS ONE
-------------------------------
Not "add thought_signature". Adding the one field we now know about leaves the same bug
in place for the next vendor extension, and we would find it the same way - in
production, from a user's screenshot.

Instead the turn CARRIES WHAT IT DOES NOT UNDERSTAND. The SDK parks any field the OpenAI
schema does not define in ``model_extra``; those fields are copied straight back onto the
message and onto each tool call. Whatever a provider attaches - today a thought
signature, tomorrow something else - survives the round trip because nothing has to
recognise it first.

Extras are read from both the message and each individual tool call, because which of the
two carries a given extension is the vendor's choice, not ours.

A pure helper is used rather than an inline block so the behaviour can be tested without
a network, a provider key, or a fake HTTP layer - the test constructs a tool call carrying
an extension and asserts it comes out the other side.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
SERVICE = ROOT / "backend/app/services/chat_service.py"
TEST = ROOT / "backend/tests/test_chat_echo.py"

report: list[str] = []
skipped: list[str] = []

OLD_BLOCK = '''        # Echo the assistant turn back, including any tool_calls in the wire shape.
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": choice.content or ""}
        if calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in calls
            ]
        convo.append(assistant_msg)
'''

NEW_BLOCK = '''        # Echo the assistant turn back INTACT - see _assistant_turn for why that matters.
        convo.append(_assistant_turn(choice, calls))
'''

HELPER = '''def _vendor_extras(obj: Any) -> dict[str, Any]:
    """Fields a provider sent that the OpenAI schema does not define.

    The SDK parks them in ``model_extra`` rather than discarding them, which is the only
    reason this is recoverable at all. Nulls are dropped: echoing an explicit null back is
    not the same as not mentioning a field, and some providers reject it.
    """
    extra = getattr(obj, "model_extra", None) or {}
    return {key: value for key, value in extra.items() if value is not None}


def _assistant_turn(choice: Any, calls: list[Any]) -> dict[str, Any]:
    """The model's own turn, ready to send back, with nothing quietly dropped.

    Rebuilding this by hand from id/name/arguments is what broke the assistant: Gemini 3
    attaches a thought signature to every function call and REQUIRES it back on the next
    turn, so the second round trip was rejected with "Function call is missing a
    thought_signature in functionCall parts". The signature was never ours to understand -
    it was ours to carry.

    So anything the provider attached rides along, on the message and on each tool call
    alike, without this code having to know what it is. The next vendor extension works
    for the same reason this one now does.
    """
    turn: dict[str, Any] = {"role": "assistant", "content": choice.content or ""}
    turn.update(_vendor_extras(choice))
    if calls:
        turn["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
                **_vendor_extras(c),
            }
            for c in calls
        ]
    return turn


'''

TEST_SRC = '''"""The assistant's turn goes back to the provider intact.

This exists because of a live failure. The loop rebuilt the model's turn from the three
fields it knew about, Gemini 3 requires a thought signature it attaches to every function
call to come back on the next turn, and so every question that needed a lookup returned
"the assistant is temporarily unavailable" after a full ten-second round trip.

The fix is not "carry thought_signature" - it is "carry what you were given". These tests
pin that property, so the next vendor extension is not another production incident.

Deliberately pure: no network, no provider key, no fake HTTP layer. The unit under test
is the shape of one message.
"""

from typing import Any

from app.services.chat_service import _assistant_turn


class _Fn:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _Call:
    """A tool call as the SDK hands it over, extensions included."""

    def __init__(self, call_id: str, fn: _Fn, extra: dict[str, Any] | None = None) -> None:
        self.id = call_id
        self.function = fn
        self.model_extra = extra or {}


class _Choice:
    def __init__(self, content: str | None, extra: dict[str, Any] | None = None) -> None:
        self.content = content
        self.model_extra = extra or {}


_SIGNATURE = {"extra_content": {"google": {"thought_signature": "Cg8KDXNpZ25hdHVyZQ=="}}}


def test_a_tool_calls_vendor_extension_survives_the_round_trip() -> None:
    # The actual regression: without this, Gemini 3 rejects the NEXT request with
    # "Function call is missing a thought_signature in functionCall parts".
    call = _Call("call_1", _Fn("get_breakdown", '{"group_by": "app"}'), _SIGNATURE)

    turn = _assistant_turn(_Choice(""), [call])

    assert turn["tool_calls"][0]["extra_content"] == _SIGNATURE["extra_content"]
    # ...and the fields the schema does define are still exactly where they were.
    assert turn["tool_calls"][0]["id"] == "call_1"
    assert turn["tool_calls"][0]["type"] == "function"
    assert turn["tool_calls"][0]["function"] == {
        "name": "get_breakdown",
        "arguments": '{"group_by": "app"}',
    }


def test_an_extension_on_the_message_itself_survives_too() -> None:
    # Which of the two carries a given extension is the vendor's choice, not ours.
    turn = _assistant_turn(_Choice("thinking", {"reasoning_details": "opaque"}), [])
    assert turn["reasoning_details"] == "opaque"
    assert turn["content"] == "thinking"


def test_nulls_are_not_echoed_back() -> None:
    # Sending an explicit null is not the same as not mentioning a field, and some
    # providers reject it. An absent extension must stay absent.
    turn = _assistant_turn(_Choice("hi", {"audio": None}), [])
    assert "audio" not in turn


def test_a_plain_answer_is_unchanged() -> None:
    # The overwhelmingly common case: no tools, no extensions, nothing added.
    assert _assistant_turn(_Choice("Revenue was $1.2M."), []) == {
        "role": "assistant",
        "content": "Revenue was $1.2M.",
    }


def test_no_content_becomes_empty_string_not_none() -> None:
    # A tool-call turn carries no text. The OpenAI wire shape wants a string there.
    turn = _assistant_turn(_Choice(None), [_Call("c", _Fn("get_totals", "{}"))])
    assert turn["content"] == ""
    assert "tool_calls" in turn


def test_an_sdk_object_without_model_extra_is_handled() -> None:
    # Not every provider's SDK exposes model_extra. Absent extensions must be absent,
    # not an AttributeError in the middle of an answer.
    class _Bare:
        content = "plain"

    class _BareCall:
        id = "c1"
        function = _Fn("get_totals", "{}")

    turn = _assistant_turn(_Bare(), [_BareCall()])
    assert turn == {
        "role": "assistant",
        "content": "plain",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "get_totals", "arguments": "{}"},
            }
        ],
    }
'''


def window(text: str, needle: str, before: int = 4, after: int = 18) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found in this file)"


def main() -> int:
    if not SERVICE.exists():
        print(f"ABORTED: missing {SERVICE}", file=sys.stderr)
        return 1

    text = SERVICE.read_text()

    if "_assistant_turn" in text:
        report.append("[echo] already applied - left alone")
    elif text.count(OLD_BLOCK) != 1:
        skipped.append(
            f"[echo] {SERVICE}: expected exactly one hand-built assistant turn, found "
            f"{text.count(OLD_BLOCK)}. Nothing was written - patching the wrong block here\n"
            "  would break every provider, not just Gemini. On disk:\n"
            + window(text, "Echo the assistant turn back")
        )
    else:
        text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
        # The helper goes directly above the loop that uses it, so the two read together.
        anchor = "async def _run_openai_loop("
        if text.count(anchor) != 1:
            skipped.append(
                f"[echo] {SERVICE}: no single `{anchor}` to sit above. Nothing was written."
            )
        else:
            at = text.index(anchor)
            text = text[:at] + HELPER + text[at:]
            SERVICE.write_text(text)
            report.append(
                f"[echo] {SERVICE}: the model's turn is echoed back intact - vendor "
                "extensions on the message and on each tool call ride along"
            )

    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: six cases pinning that nothing is dropped")
    else:
        skipped.append(f"[test] {TEST.parent} does not exist - no test was written.")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    print(
        "\nIf Gemini still refuses after this, the fallback is a model that does not use\n"
        "thought signatures at all - GEMINI_MODEL=gemini-2.5-flash in .env, then restart\n"
        "the backend. That is a workaround; this is the fix."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

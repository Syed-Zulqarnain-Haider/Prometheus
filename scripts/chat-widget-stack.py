#!/usr/bin/env python3
"""The assistant goes to the top of the corner stack, and stops being sat on.

Three separate fixed elements share the bottom-right corner and nothing coordinates
them. The privacy shield and the announcement button sit at ``z-[60]``; the assistant's
container sits at ``z-50``. So when the panel is open, the two little buttons render ON
TOP of it - over the composer, over the send button. That is the overlap.

  A. Z-ORDER.  The assistant's container moves to ``z-[70]``. An open panel now covers
     the two buttons instead of being covered by them. They are conveniences; the panel
     is the task. Nothing has to be hidden, and no cross-component state is invented to
     coordinate it - the layer order simply says which one wins.

  B. TOP OF THE STACK.  The container swaps its ``bottom-4`` class for the same
     ``calc(<N>rem + 1cm + env(safe-area-inset-bottom, 0px))`` the other two use, at
     9rem - above the privacy shield at 5rem. That puts the launcher where it was asked
     to be, and it also means float-bubbles.py can see and manage it from now on, rather
     than reporting it as "positioned some other way" and stepping around it.

  C. THE PANEL STOPS RIDING THE LAUNCHER UP.  The panel was a flex SIBLING of the
     launcher, so lifting the launcher would have lifted the panel with it - and a 32rem
     panel raised by 9rem runs off the top of a short window, taking its own header with
     it. It becomes ``absolute bottom-full``, growing upward from the launcher, and its
     height is clamped to the space actually above it. The launcher can now be moved
     without the panel being pushed off-screen.

Every anchor must match exactly once, or nothing is written and the region is printed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
WIDGET = ROOT / "frontend/components/chat/chat-widget.tsx"

# The launcher's rung. 9rem clears the privacy shield's 5rem with room to spare, and
# uses the same shape as the others so one script can manage the whole stack.
LAUNCHER_BOTTOM = "9rem"
# Reserved above the launcher: its own height, the gap, and its offset from the floor.
# The panel is clamped to whatever is left, so it can never be taller than the window.
RESERVED = "17rem"

CONTAINER_RE = re.compile(
    r'(?P<indent>[ \t]*)<div className="fixed bottom-4 right-4 z-50 '
    r'flex flex-col items-end gap-3 print:hidden">'
)
PANEL_RE = re.compile(
    r'(?P<indent>[ \t]*)<div className="flex h-\[min\(32rem,80vh\)\] '
    r"w-\[min\(24rem,calc\(100vw-2rem\)\)\] flex-col overflow-hidden rounded-xl "
    r'border bg-card shadow-2xl">'
)

CONTAINER_NEW = """{indent}<div
{indent}  // Top of the corner stack, above the privacy shield and the announcement
{indent}  // button - and above them in Z-ORDER too, so an open panel covers those two
{indent}  // rather than being covered by them. Same bottom: calc(...) shape they use, so
{indent}  // the whole stack can be moved by one script instead of three special cases.
{indent}  style={{{{ bottom: "calc({bottom} + 1cm + env(safe-area-inset-bottom, 0px))" }}}}
{indent}  className="fixed right-4 z-[70] flex flex-col items-end print:hidden"
{indent}>"""

PANEL_NEW = """{indent}<div className="absolute bottom-full right-0 mb-3 flex \
h-[min(32rem,calc(100vh-{reserved}))] w-[min(24rem,calc(100vw-2rem))] flex-col \
overflow-hidden rounded-xl border bg-card shadow-2xl">"""


def window(text: str, needle: str, before: int = 3, after: int = 8) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(
                f"      | {ln}" for ln in lines[max(0, i - before) : i + after]
            )
    return "      | (not found anywhere in the file)"


def main() -> int:
    if not WIDGET.exists():
        print(f"ABORTED: missing {WIDGET}", file=sys.stderr)
        return 1

    text = WIDGET.read_text()
    if "z-[70]" in text and "bottom-full" in text:
        print("Already applied - left alone.")
        return 0

    failures: list[str] = []
    for label, pattern, needle in (
        ("the launcher container", CONTAINER_RE, "flex flex-col items-end gap-3"),
        ("the panel", PANEL_RE, "min(32rem,80vh)"),
    ):
        hits = len(pattern.findall(text))
        if hits != 1:
            failures.append(
                f"[{label}] expected exactly one match, found {hits}. On disk:\n"
                + window(text, needle)
            )
    if failures:
        print("ABORTED - nothing was written.\n", file=sys.stderr)
        for entry in failures:
            print(entry + "\n", file=sys.stderr)
        return 1

    # Panel first: rewriting the container does not move the panel's offset, but doing
    # the deeper one first keeps the two edits independent of each other's lengths.
    panel = PANEL_RE.search(text)
    assert panel is not None
    text = (
        text[: panel.start()]
        + PANEL_NEW.format(indent=panel.group("indent"), reserved=RESERVED)
        + text[panel.end() :]
    )

    container = CONTAINER_RE.search(text)
    assert container is not None
    text = (
        text[: container.start()]
        + CONTAINER_NEW.format(indent=container.group("indent"), bottom=LAUNCHER_BOTTOM)
        + text[container.end() :]
    )

    WIDGET.write_text(text)

    print(
        "PATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    print(
        f"  - launcher raised to calc({LAUNCHER_BOTTOM} + 1cm + safe-area), above the"
    )
    print("    privacy shield at 5rem + 1cm and the announcement button at 1rem + 1cm")
    print("  - container z-50 -> z-[70]: an open panel now covers those two buttons")
    print(
        "  - the panel hangs off the launcher (absolute bottom-full) instead of being"
    )
    print(f"    its flex sibling, and is clamped to 100vh - {RESERVED} so raising the")
    print(
        "    launcher cannot push the panel's own header off the top of a short window"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

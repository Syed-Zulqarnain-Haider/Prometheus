#!/usr/bin/env python3
"""Raise the floating buttons by a centimetre, and put the assistant on top of the stack.

The bubbles in the bottom-right corner each place themselves independently, with
``bottom: calc(<N>rem + env(safe-area-inset-bottom, 0px))``. Different values of N are
what stack them; the env() term is what keeps the lowest one clear of the iPhone home
indicator.

  A. UP ONE CENTIMETRE.  ``+ 1cm`` is added to every one of them - literally a
     centimetre, in CSS's own unit, rather than a pixel count that approximates one and
     then has to be explained. Adding the same amount to each preserves the spacing
     between them, so the stack moves as a stack.

  B. ASSISTANT ON TOP.  The rungs of the ladder are left exactly as they are; the
     assistant simply swaps rungs with whichever bubble currently sits highest. Nothing
     is invented, nothing else moves, and the gaps stay whatever they already were.

Both are idempotent, and neither guesses: the bubbles are DISCOVERED by their positioning
code, and the assistant is identified from the file it lives in. If it cannot be picked
out, the raise still applies and the ordering is reported rather than attempted. Anything
fixed to the bottom that does NOT use this pattern is printed at the end, so a bubble
positioned some other way cannot silently be left behind.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
RAISE = "1cm"

# bottom: "calc(5rem + env(safe-area-inset-bottom, 0px))", with or without an existing
# raise already applied.
BOTTOM_RE = re.compile(
    r'bottom:\s*"calc\(\s*(?P<rem>[\d.]+)rem\s*'
    r"(?:\+\s*(?P<raise>[\d.]+)(?:cm|px|rem)\s*)?"
    r'\+\s*env\(safe-area-inset-bottom,\s*0px\)\s*\)"'
)
# Anything else pinned to the bottom of the viewport - reported, never touched.
OTHER_FIXED_RE = re.compile(r"fixed[^\"']*\bbottom-[\w.\[\]]+")

ASSISTANT = re.compile(r"chat|assistant|advisor", re.I)

skipped: list[str] = []
notes: list[str] = []


def frontend_files() -> list[Path]:
    return sorted(
        p
        for p in ROOT.glob("frontend/**/*.tsx")
        if "node_modules" not in p.parts and ".next" not in p.parts
    )


class Bubble:
    def __init__(self, path: Path, match: re.Match[str]) -> None:
        self.path = path
        self.start = match.start()
        self.end = match.end()
        self.rem = float(match.group("rem"))

    def render(self, rem: float) -> str:
        # Trailing .0 would be noise in the stylesheet; 5.5rem must survive intact.
        value = f"{rem:g}"
        return (
            f'bottom: "calc({value}rem + {RAISE} + env(safe-area-inset-bottom, 0px))"'
        )


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    files = frontend_files()
    found: dict[Path, list[Bubble]] = {}
    for path in files:
        matches = list(BOTTOM_RE.finditer(path.read_text()))
        if matches:
            found[path] = [Bubble(path, m) for m in matches]

    if not found:
        print(
            "ABORTED - nothing was written.\n\nNo floating button uses "
            '`bottom: "calc(<N>rem + env(safe-area-inset-bottom, 0px))"`. Everything '
            "pinned to the bottom of the viewport:",
            file=sys.stderr,
        )
        report_others(files)
        return 1

    print("The stack, as it is on disk:")
    for path, bubbles in found.items():
        for bubble in bubbles:
            print(f"  {bubble.rem:>5g}rem  {path}")

    # ── B. Work out the swap BEFORE writing, so one pass produces the final value. ──
    single = {p: b[0] for p, b in found.items() if len(b) == 1}
    assistants = [p for p in single if ASSISTANT.search(str(p))]
    swap: dict[Path, float] = {}

    if len(assistants) != 1:
        skipped.append(
            f"[assistant-on-top] {len(assistants)} of the bubbles look like the "
            "assistant, so which one to raise is a guess - the ordering is left alone. "
            "Files carrying exactly one bubble: " + ", ".join(str(p) for p in single)
        )
    elif len(single) < 2:
        skipped.append(
            "[assistant-on-top] only one bubble places itself this way - there is no "
            "stack to reorder."
        )
    else:
        chat = assistants[0]
        highest = max(single, key=lambda p: single[p].rem)
        if highest == chat:
            notes.append(
                "[assistant-on-top] the assistant is already the highest - left alone"
            )
        else:
            swap[chat] = single[highest].rem
            swap[highest] = single[chat].rem
            notes.append(
                f"[assistant-on-top] {chat.name} and {highest.name} swap rungs "
                f"({single[chat].rem:g}rem <-> {single[highest].rem:g}rem)"
            )

    # ── A. Write every bubble at its final height, back to front per file. ──
    raised = 0
    for path, bubbles in found.items():
        text = path.read_text()
        for bubble in reversed(bubbles):
            rem = swap.get(path, bubble.rem) if len(bubbles) == 1 else bubble.rem
            text = text[: bubble.start] + bubble.render(rem) + text[bubble.end :]
            raised += 1
        path.write_text(text)

    print(
        "\nPATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    print(f"  - {raised} bubble(s) raised by {RAISE}, spacing between them unchanged")
    for note in notes:
        print(f"  - {note}")
    for entry in skipped:
        print(f"\n{entry}")

    print("\nThe stack now:")
    for path in found:
        for match in BOTTOM_RE.finditer(path.read_text()):
            raise_term = match.group("raise")
            print(
                f"  {float(match.group('rem')):>5g}rem"
                f" + {raise_term or '0'}{'' if raise_term is None else 'cm'}  {path}"
            )

    report_others(files)
    return 0


def report_others(files: list[Path]) -> None:
    print("\nAlso pinned to the bottom, positioned some other way (NOT touched):")
    any_found = False
    for path in files:
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if OTHER_FIXED_RE.search(line):
                print(f"  {path}:{i}  {line.strip()[:110]}")
                any_found = True
    if not any_found:
        print("  (none)")


if __name__ == "__main__":
    raise SystemExit(main())

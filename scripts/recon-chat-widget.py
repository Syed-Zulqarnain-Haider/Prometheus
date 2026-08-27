#!/usr/bin/env python3
"""Read-only: why the assistant opens into an empty panel.

Writes nothing. Prints the widget, whatever decides it is available, and the announcement
bar for comparison - the control that opens correctly.

The panel opening at all means the widget is mounted and its trigger works, so the fault
is inside: either it is rendering a branch with no content (not configured, not enabled,
no messages yet and no empty state), or the content is there and something is collapsing
it. Those look identical from outside and are fixed in completely different places, so
this reads the code rather than guessing between them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")

# Whatever the widget is called, it will mention at least one of these.
FINGERPRINTS = (
    "useSendChat",
    "chat_enabled",
    "assistant",
    "Assistant",
    "advisor",
    "Advisor",
)
NAME_HINTS = ("advisor", "chat-widget", "assistant", "chat-fab", "chat-panel")


def dump(path: Path, *, whole: bool = True, needles: tuple[str, ...] = ()) -> None:
    lines = path.read_text().splitlines()
    print(f"\n{'=' * 72}\n{path}  ({len(lines)} lines)\n{'=' * 72}")
    if whole:
        for i, line in enumerate(lines, 1):
            print(f"  {i:>4}  {line}")
        return
    wanted: set[int] = set()
    for i, line in enumerate(lines):
        if any(n in line for n in needles):
            wanted.update(range(max(0, i - 5), min(len(lines), i + 12)))
    last = -2
    for i in sorted(wanted):
        if i != last + 1:
            print("        ...")
        print(f"  {i + 1:>4}  {lines[i]}")
        last = i


def frontend_files() -> list[Path]:
    out: list[Path] = []
    for pattern in ("frontend/**/*.tsx", "frontend/**/*.ts"):
        for path in ROOT.glob(pattern):
            if "node_modules" in path.parts or ".next" in path.parts:
                continue
            out.append(path)
    return sorted(set(out))


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    files = frontend_files()

    # 1. The widget itself - by name first, then by what it must reference.
    by_name = [p for p in files if any(h in p.name.lower() for h in NAME_HINTS)]
    by_content = [
        p
        for p in files
        if p not in by_name and any(f in p.read_text() for f in FINGERPRINTS)
    ]

    print("### THE ASSISTANT WIDGET")
    if not by_name and not by_content:
        print("  Nothing under frontend/ mentions the assistant at all.")
    for path in by_name:
        dump(path)
    for path in by_content:
        # These are usually large pages that merely reference it - show the region only.
        dump(path, whole=False, needles=FINGERPRINTS)

    # 2. The announcement bar - the control that opens correctly, for comparison.
    print("\n\n### THE ANNOUNCEMENT BAR (the one that works)")
    bar = ROOT / "frontend/components/layout/announcement-bar.tsx"
    if bar.exists():
        dump(bar)
    else:
        print(f"  MISSING: {bar}")

    # 3. What the client is told about availability.
    print("\n\n### WHAT DECIDES 'AVAILABLE'")
    for path in files:
        text = path.read_text()
        if "chat" in text.lower() and re.search(r"available|configured|enabled", text):
            hits = [
                f"  {path}:{i + 1}  {line.strip()}"
                for i, line in enumerate(text.splitlines())
                if re.search(r"chat.*(available|configured|enabled)", line, re.I)
                or re.search(r"(available|configured|enabled).*chat", line, re.I)
            ]
            if hits:
                print("\n".join(hits))

    # 4. The server side of the same question.
    print("\n\n### BACKEND: the assistant's routes and its status endpoint")
    for rel in ("backend/app/api/v1/chat.py", "backend/app/services/chat_service.py"):
        path = ROOT / rel
        if not path.exists():
            print(f"  MISSING: {path}")
            continue
        dump(
            path,
            whole=False,
            needles=("@router", "available", "configured", "chat_enabled", "def "),
        )

    print("\n\nNothing was written. This run only read files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

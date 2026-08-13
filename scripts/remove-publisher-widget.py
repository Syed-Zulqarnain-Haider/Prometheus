#!/usr/bin/env python3
"""Remove the Publisher Performance table from Executive Overview (owner request).

HOU Performance covers the same per-game metrics led by the dimension the owner actually
reads, so the publisher-led duplicate goes. Four removals:

  components/overview/overview-client.tsx  - the import and the registry entry
  lib/overview-layout.ts                   - the id and its default grid placement

``publisher-table.tsx`` itself is LEFT ON DISK - unrendered, not deleted, so it can be
re-registered later without rewriting it (which is exactly how hou-table.tsx survived).

Anchored: every line must appear EXACTLY once or nothing is written. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path("frontend/components/overview/overview-client.tsx")
LAYOUT = Path("frontend/lib/overview-layout.ts")

CLIENT_LINES = [
    'import { PublisherTable } from "@/components/overview/publisher-table";\n',
    "    publisher: <PublisherTable filters={filters} />,\n",
]
LAYOUT_LINES = [
    '  "publisher",\n',
    '  { i: "publisher", x: 0, y: 16, w: 12, h: 18, minW: 4, minH: 10 },\n',
]


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def strip(path: Path, lines: list[str]) -> bool:
    text = path.read_text()
    if not any(line in text for line in lines):
        return False
    for line in lines:
        if text.count(line) != 1:
            die(f"{path}: expected exactly one {line.strip()!r}, found {text.count(line)}")
    for line in lines:
        text = text.replace(line, "", 1)
    path.write_text(text)
    return True


def main() -> None:
    for path in (CLIENT, LAYOUT):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    client_done = strip(CLIENT, CLIENT_LINES)
    layout_done = strip(LAYOUT, LAYOUT_LINES)

    if not client_done and not layout_done:
        print("already removed - nothing to do")
        return
    print(f"patched {CLIENT}" if client_done else f"{CLIENT}: already removed")
    print(f"patched {LAYOUT}" if layout_done else f"{LAYOUT}: already removed")
    print("\nPublisher Performance is gone from Executive Overview.")
    print("Anyone with a SAVED layout that still lists it should press Reset once.")


if __name__ == "__main__":
    main()

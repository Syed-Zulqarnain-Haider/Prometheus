#!/usr/bin/env python3
"""Register the existing HOU Performance table as an Overview widget.

``components/overview/hou-table.tsx`` is already written and working, but it was never
added to the widget registry or the default layout - so it never rendered. This wires it
in beside Publisher Performance:

  components/overview/overview-client.tsx  - import + one registry entry
  lib/overview-layout.ts                   - the id + its default grid placement

Anchored patch: every anchor must appear EXACTLY once or nothing is written. Idempotent -
a second run reports "already registered" and changes nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path("frontend/components/overview/overview-client.tsx")
LAYOUT = Path("frontend/lib/overview-layout.ts")
TABLE = Path("frontend/components/overview/hou-table.tsx")

IMPORT_ANCHOR = 'import { PublisherTable } from "@/components/overview/publisher-table";\n'
IMPORT_ADD = 'import { HouTable } from "@/components/overview/hou-table";\n'

ITEM_ANCHOR = "    publisher: <PublisherTable filters={filters} />,\n"
ITEM_ADD = "    hou: <HouTable filters={filters} />,\n"

ID_ANCHOR = '  "publisher",\n'
ID_ADD = '  "hou",\n'

# Placed directly BELOW the publisher table (y = its y + its h), full width, same shape.
GRID_ANCHOR = '  { i: "publisher", x: 0, y: 16, w: 12, h: 18, minW: 4, minH: 10 },\n'
GRID_ADD = '  { i: "hou", x: 0, y: 34, w: 12, h: 18, minW: 4, minH: 10 },\n'


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def patch(path: Path, edits: list[tuple[str, str]], marker: str, *, before: bool) -> bool:
    """Apply (anchor, addition) pairs. Returns False when already patched."""
    text = path.read_text()
    if marker in text:
        return False
    for anchor, _ in edits:
        if text.count(anchor) != 1:
            die(f"{path}: expected exactly one {anchor.strip()!r}, found {text.count(anchor)}")
    for anchor, addition in edits:
        replacement = addition + anchor if before else anchor + addition
        text = text.replace(anchor, replacement, 1)
    path.write_text(text)
    return True


def main() -> None:
    for path in (CLIENT, LAYOUT, TABLE):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    # HouTable must actually be exported, or the build breaks on an unknown import.
    if "export function HouTable" not in TABLE.read_text():
        die(f"{TABLE} does not export HouTable - check its export name before wiring it up")

    # Import goes BEFORE the publisher import ("hou-table" sorts before "publisher-table",
    # which is what eslint's import ordering expects); the registry entry goes before the
    # publisher entry so HOU reads first.
    client_done = patch(CLIENT, [(IMPORT_ANCHOR, IMPORT_ADD), (ITEM_ANCHOR, ITEM_ADD)], "HouTable", before=True)
    layout_done = patch(LAYOUT, [(ID_ANCHOR, ID_ADD), (GRID_ANCHOR, GRID_ADD)], '"hou"', before=True)

    if not client_done and not layout_done:
        print("already registered - nothing to do")
        return
    print(f"patched {CLIENT}" if client_done else f"{CLIENT}: already registered")
    print(f"patched {LAYOUT}" if layout_done else f"{LAYOUT}: already registered")
    print("\nHOU Performance will appear under Publisher Performance on Executive Overview.")
    print("Users with a SAVED layout keep theirs - they can add it via Customize layout,")
    print("or use Reset to pick up the new default.")


if __name__ == "__main__":
    main()

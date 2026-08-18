#!/usr/bin/env python3
"""Centre the collapsed sidebar. Four real geometry bugs, not taste.

The rail is 56px (w-14) and each item is a 40px circle (h-10 w-10) centred with mx-auto.
It should have looked centred. It did not, for four separate reasons:

1. THE ICONS SIT 6px LEFT OF THEIR OWN CIRCLE. The label span deliberately stays MOUNTED
   at w-0 when collapsed (unmounting it mid-animation reflows every row at once) - but a
   zero-width span is still a flex child, so the shared ``gap-3`` puts 12px of real space
   between the icon and nothing. Flex content becomes 16 + 12 + 0 = 28px centred in 40px,
   which starts the icon at 6px instead of 12px. Every icon in the rail is off-centre by
   half the gap. The gap moves to the EXPANDED branch, where there is actually a label to
   separate.

2. THE "P" IS NOT OVER THE ICON COLUMN. The header is ``px-4``, so the logo starts 16px
   from the edge while the bubbles below are centred at 28px - the logo reads about 7px
   left of everything it heads. Collapsed, the header holds only the "P" (the reorder
   button is hidden), so it centres.

3. A DIVIDER ABOVE THE FIRST GROUP. The group rule renders for every section including
   the first, which puts a line directly under the header separating it from nothing.

4. THE DIVIDERS ARE A DIFFERENT WIDTH FROM THE BUBBLES. ``mx-2`` inside the nav's ``p-2``
   makes each rule 24px wide against 40px bubbles - two centred widths that disagree,
   which is what reads as ragged even once the icons are fixed. They now match the
   bubbles.

Nothing here changes behaviour, only class strings and one index guard: no new imports,
no new props, no state.

Anchored: every anchor must appear EXACTLY once or NOTHING is written. Idempotent.
Frontend rebuild; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

SIDEBAR = Path("frontend/components/layout/sidebar.tsx")

# ── 1. the gap that pushed every icon off-centre ──────────────────────────────
BASE_ANCHOR = '          "relative flex items-center gap-3 text-sm",\n'
BASE_NEW = (
    "          // No gap on the shared base: the label span stays MOUNTED at w-0 when\n"
    "          // collapsed, and a zero-width span is still a flex child - so gap-3 put\n"
    "          // 12px of real space inside a 40px circle and started every icon 6px left\n"
    "          // of its own centre. The gap belongs to the expanded branch, where there\n"
    "          // is actually a label to separate.\n"
    '          "relative flex items-center text-sm",\n'
)

EXPANDED_ANCHOR = '                "rounded-md px-3 py-2 hover:translate-x-0.5",\n'
EXPANDED_NEW = '                "gap-3 rounded-md px-3 py-2 hover:translate-x-0.5",\n'

# ── 2. the logo that did not sit over the icons ───────────────────────────────
HEADER_ANCHOR = '      <div className="flex h-14 items-center justify-between border-b px-4">\n'
HEADER_NEW = """      <div
        className={cn(
          "flex h-14 items-center border-b",
          // Collapsed, the header holds only the "P" - and px-4 started it 16px from the
          // edge while the bubbles below are centred at 28px. Centre it over the column
          // it heads.
          collapsed ? "justify-center px-0" : "justify-between px-4",
        )}
      >
"""

# ── 3 + 4. the group rules ────────────────────────────────────────────────────
MAP_ANCHOR = "          {sections.map((section) => (\n"
MAP_NEW = "          {sections.map((section, groupIndex) => (\n"

RULE_ANCHOR = '                <div className="mx-2 mb-1 border-t" aria-hidden />\n'
RULE_NEW = (
    "                // No rule before the FIRST group - it would separate it from\n"
    "                // nothing. Width matches the bubbles (w-10) rather than mx-2, so the\n"
    "                // two centred widths stop disagreeing.\n"
    "                groupIndex > 0 && (\n"
    '                  <div className="mx-auto mb-1 w-10 border-t" aria-hidden />\n'
    "                )\n"
)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not SIDEBAR.exists():
        die(f"{SIDEBAR} not found - run from the repository root")

    text = SIDEBAR.read_text()

    if "groupIndex" in text and '"relative flex items-center text-sm"' in text:
        print(f"{SIDEBAR}: already aligned")
        return

    # The collapsed rail must actually exist in this file, or these anchors are being
    # applied to a sidebar that has no rail to centre.
    for token in ("collapsed", "mx-auto h-10 w-10", "const sections"):
        if token not in text:
            die(f"{SIDEBAR}: {token!r} not found - this is not the collapsible sidebar")

    edits = [
        (BASE_ANCHOR, BASE_NEW),
        (EXPANDED_ANCHOR, EXPANDED_NEW),
        (HEADER_ANCHOR, HEADER_NEW),
        (MAP_ANCHOR, MAP_NEW),
        (RULE_ANCHOR, RULE_NEW),
    ]
    for anchor, _ in edits:
        if text.count(anchor) != 1:
            die(f"{SIDEBAR}: expected exactly one {anchor.strip()[:60]!r}, found {text.count(anchor)}")

    for anchor, replacement in edits:
        text = text.replace(anchor, replacement, 1)
    SIDEBAR.write_text(text)
    print(f"patched {SIDEBAR}: icons centred, logo over the column, group rules tidied")
    print("Frontend rebuild applies it.")


if __name__ == "__main__":
    main()

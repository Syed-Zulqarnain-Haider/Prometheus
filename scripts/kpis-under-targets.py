#!/usr/bin/env python3
"""Move the KPI strip below the three progress-to-target cards.

The KPI row was a FIXED header rendered above the draggable grid - deliberately, on the
grounds that a five-card strip in a grid cell would get clipped. That reason has since
stopped being true: the grid measures each widget with a ResizeObserver and grows the
cell to fit, so nothing in it can be clipped by a saved arrangement any more.

So rather than special-casing the strip's position a second time, it JOINS the grid as a
full-width widget placed directly under the first row. Two things follow from that:

  * it lands exactly where it was asked to go, under the targets/trend row, on desktop
    and in the stacked mobile order alike;
  * it becomes draggable like everything else, so the next time its position is wrong it
    is a drag rather than a deploy.

WHAT HAPPENS TO A SAVED ARRANGEMENT
-----------------------------------
Nothing is wiped. ``normalizeLayouts`` gives a widget the layout has never seen its
default position, and the grid's vertical compaction settles the result - so someone who
dragged their dashboard into shape keeps that shape, with the strip inserted near the
top. If they do not like where it lands, it is one drag, and "Reset to default" in the
layout editor is already there. Deleting everyone's arrangement to guarantee a tidy first
render would cost more than it buys.

The insertion point is COMPUTED from the layout rather than hardcoded: whatever currently
sits on the first row, the strip goes directly beneath it and everything below shifts
down by its height. So this stays correct if the first row is rearranged later.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
LAYOUT = ROOT / "frontend/lib/overview-layout.ts"
CLIENT = ROOT / "frontend/components/overview/overview-client.tsx"

ITEM_ID = "kpis"
# Full width, and about as tall as the other single-row card strip. The ResizeObserver
# grows it if the cards reflow taller, so this is a starting height, not a cap.
KPI_H = 5
KPI_MIN_H = 4
KPI_MIN_W = 6

report: list[str] = []
skipped: list[str] = []

# A "row N: ..." line in the comment above LG_LAYOUT, plus any indented continuation.
ROW_ENUM_RE = re.compile(r"^//\s+row \d+:.*\n(?:^//\s{5,}\S.*\n)*", re.M)

ENTRY_RE = re.compile(
    r"\{\s*i:\s*\"(?P<id>[^\"]+)\"\s*,\s*x:\s*(?P<x>\d+)\s*,\s*y:\s*(?P<y>\d+)\s*,"
    r"\s*w:\s*(?P<w>\d+)\s*,\s*h:\s*(?P<h>\d+)(?P<rest>[^}]*)\}"
)


def window(text: str, needle: str, before: int = 3, after: int = 14) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found in this file)"


def array_span(text: str, header: re.Pattern[str]) -> tuple[int, int] | None:
    """Byte range BETWEEN the brackets of an array literal introduced by ``header``."""
    match = header.search(text)
    if match is None:
        return None
    open_at = text.find("[", match.end() - 1)
    if open_at == -1:
        return None
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return open_at + 1, i
    return None


def section_layout() -> bool:
    label = "layout"
    if not LAYOUT.exists():
        skipped.append(f"[{label}] {LAYOUT} does not exist here - nothing changed.")
        return False
    text = LAYOUT.read_text()
    if f'"{ITEM_ID}"' in text:
        report.append(f"[{label}] the strip is already a grid widget - left alone")
        return True

    lg = array_span(text, re.compile(r"const LG_LAYOUT\s*:\s*Layout\[\]\s*="))
    ids = array_span(text, re.compile(r"export const OVERVIEW_ITEM_IDS\s*="))
    if lg is None or ids is None:
        skipped.append(
            f"[{label}] {LAYOUT}: could not find both LG_LAYOUT and OVERVIEW_ITEM_IDS as\n"
            "  bracketed arrays. Nothing was changed.\n" + window(text, "LG_LAYOUT")
        )
        return False

    body = text[lg[0] : lg[1]]
    entries = list(ENTRY_RE.finditer(body))
    if not entries:
        skipped.append(
            f"[{label}] {LAYOUT}: LG_LAYOUT holds no recognisable "
            '{ i: "...", x, y, w, h } entries. Nothing was changed.\n' + window(text, "LG_LAYOUT")
        )
        return False

    first_row = [e for e in entries if int(e.group("y")) == 0]
    if not first_row:
        skipped.append(
            f"[{label}] {LAYOUT}: nothing sits on the first row (y: 0), so 'directly "
            "underneath it' has no meaning here. Nothing was changed."
        )
        return False
    bottom = max(int(e.group("y")) + int(e.group("h")) for e in first_row)
    last_first_row = first_row[-1]

    # Rebuilt rather than patched in place: every y below the first row moves, and
    # splicing ten independent edits into one string is how off-by-one bugs get in.
    lines: list[str] = []
    for entry in entries:
        y = int(entry.group("y"))
        shifted = y + KPI_H if y >= bottom else y
        lines.append(
            f'  {{ i: "{entry.group("id")}", x: {entry.group("x")}, y: {shifted}, '
            f'w: {entry.group("w")}, h: {entry.group("h")}{entry.group("rest").rstrip()} }},'
        )
        if entry is last_first_row:
            lines.append(
                f'  {{ i: "{ITEM_ID}", x: 0, y: {bottom}, w: 12, h: {KPI_H}, '
                f"minW: {KPI_MIN_W}, minH: {KPI_MIN_H} }},"
            )
    text = text[: lg[0]] + "\n" + "\n".join(lines) + "\n" + text[lg[1] :]

    # The id list is visual order, and stacked() reads it for the mobile order - so the
    # strip goes in at the same place it sits on the desktop grid, not on the end.
    ids = array_span(text, re.compile(r"export const OVERVIEW_ITEM_IDS\s*="))
    assert ids is not None
    id_body = text[ids[0] : ids[1]]
    anchor = re.search(rf'"{re.escape(last_first_row.group("id"))}",', id_body)
    if anchor is None:
        skipped.append(
            f"[{label}] {LAYOUT}: OVERVIEW_ITEM_IDS does not list "
            f'"{last_first_row.group("id")}", so where to put the strip in the mobile\n'
            "  order is a guess. Nothing was changed."
        )
        return False
    at = ids[0] + anchor.end()
    text = text[:at] + f'\n  "{ITEM_ID}",' + text[at:]

    # The two comments that say the strip is NOT in the grid are now the opposite of true.
    text = text.replace(
        "/** Draggable widget ids, in default visual order. The KPI row is NOT here - it is a\n"
        " *  fixed full-width header rendered above the grid (never draggable, never clipped). */",
        "/** Draggable widget ids, in default visual order - the KPI strip among them. It used\n"
        " *  to be a fixed header above the grid, on the grounds that a five-card strip in a\n"
        " *  cell would clip; the grid now measures each widget and grows its cell to fit, so\n"
        " *  that reason is gone and the strip can be moved like anything else. */",
    )
    text = text.replace(
        "// The default desktop arrangement for the DRAGGABLE area (everything below the fixed\n"
        "// KPI header):",
        "// The default desktop arrangement:",
    )
    # The row-by-row enumeration above the array is now off by one everywhere and cannot
    # be kept honest by hand every time something moves. Replaced with a description of
    # the SHAPE, which the array itself then spells out exactly.
    rows = list(ROW_ENUM_RE.finditer(text))
    if rows:
        summary = (
            "//   row 1 is the two target donuts with the trend chart between them; the KPI\n"
            "//   strip sits full width directly beneath them, and the tables and charts\n"
            "//   follow. The array below is the authority - this is only its shape.\n"
        )
        text = ROW_ENUM_RE.sub("", text)
        at = rows[0].start()
        text = text[:at] + summary + text[at:]
    else:
        report.append(
            f"[{label}] the row-by-row comment above LG_LAYOUT was not in the expected "
            "shape, so it was left as-is - check it still describes the array"
        )

    LAYOUT.write_text(text)
    report.append(
        f"[{label}] {LAYOUT}: the KPI strip is a full-width widget at y={bottom}, directly "
        f"under the first row; everything below it moved down {KPI_H} rows"
    )
    return True


KPI_LINE_RE = re.compile(r"^[ \t]*<KpiRow\b[^>]*/>[ \t]*\n", re.M)
COMMENT_LINE_RE = re.compile(r"^[ \t]*\{/\*.*\*/\}[ \t]*\n", re.M)
ITEMS_OPEN_RE = re.compile(r"const items\s*:\s*Record<OverviewItemId,\s*ReactNode>\s*=\s*\{\n")


def section_client() -> None:
    label = "overview page"
    if not CLIENT.exists():
        skipped.append(f"[{label}] {CLIENT} does not exist here - nothing changed.")
        return
    text = CLIENT.read_text()
    if f"{ITEM_ID}:" in text and "<KpiRow" in text and not KPI_LINE_RE.search(text):
        report.append(f"[{label}] already a grid widget - left alone")
        return

    hits = KPI_LINE_RE.findall(text)
    if len(hits) != 1:
        skipped.append(
            f"[{label}] {CLIENT}: expected exactly one standalone <KpiRow ... /> line, "
            f"found {len(hits)}. Nothing was changed.\n" + window(text, "<KpiRow")
        )
        return
    element = hits[0].strip()

    match = KPI_LINE_RE.search(text)
    assert match is not None
    start, end = match.start(), match.end()
    # Take the explanatory comment directly above it too - it describes an arrangement
    # that is about to stop existing, and a stale comment is worse than none.
    preceding = COMMENT_LINE_RE.search(text[:start], max(0, start - 400))
    if preceding is not None and preceding.end() == start and "KPI" in preceding.group(0):
        start = preceding.start()
    text = text[:start] + text[end:]
    text = re.sub(r"\n{3,}", "\n\n", text)

    opening = ITEMS_OPEN_RE.search(text)
    if opening is None:
        skipped.append(
            f"[{label}] {CLIENT}: no `const items: Record<OverviewItemId, ReactNode> = {{`\n"
            "  to add the strip to - nothing was written, so the page is unchanged.\n"
            + window(text, "OverviewItemId")
        )
        return
    # The element is reused verbatim, so whatever props it was given still reach it.
    text = text[: opening.end()] + f"    {ITEM_ID}: {element},\n" + text[opening.end() :]

    text = text.replace(
        "The KPI row is a FIXED full-width\n"
        "  // header (below) and is intentionally NOT part of the draggable grid.",
        "The KPI strip is one of them: it sits\n"
        "  // directly under the first row and moves like any other widget.",
    )
    text = text.replace(
        """      {/* Everything below the KPIs is the draggable/resizable grid. In view mode it is
          static but still laid out by the saved positions, so the arrangement persists
          outside the editor. Stacks to a single column below the lg breakpoint. */}""",
        """      {/* The whole dashboard is one draggable/resizable grid. In view mode it is
          static but still laid out by the saved positions, so the arrangement persists
          outside the editor. Stacks to a single column below the lg breakpoint. */}""",
    )

    CLIENT.write_text(text)
    report.append(f"[{label}] {CLIENT}: the KPI strip renders inside the grid, not above it")


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    # The page must not stop rendering the strip unless the grid has a place for it.
    if section_layout():
        section_client()
    else:
        skipped.append(
            "[overview page] left alone: the grid has no slot for the strip, and taking it\n"
            "  off the page before there is somewhere for it to go would lose it entirely."
        )

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    print(
        "\nAnyone who had dragged their own arrangement keeps it; the strip is inserted at\n"
        "its default spot and the grid settles the rest. 'Reset to default' in the layout\n"
        "editor puts everything back to this new arrangement."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

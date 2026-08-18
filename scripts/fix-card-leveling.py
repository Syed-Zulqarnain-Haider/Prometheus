#!/usr/bin/env python3
"""Make widgets FILL their grid cells, so equal outer heights mean level content.

The grid already equalizes the donut - trend - donut row to the tallest member
(EQUAL_HEIGHT_GROUPS), so the OUTER boxes match - but the widgets inside rendered at
natural content height, hugging the top of the cell with dead space below, each ending
at a different line. Matched frames, ragged content.

Two changes:

  frontend/components/overview/dashboard-grid.tsx
      The measured wrapper becomes h-full and stretches each widget's root to the cell
      ([&>*]:h-full). That was previously impossible because the wrapper's
      offsetHeight fed the auto-height minH: a stretched wrapper measures the CELL,
      not the content, and minH would pin to whatever height the cell happened to
      have - the editor could never shrink a widget again. The measurement therefore
      changes to CLIP-AWARE: report only when scrollHeight exceeds the box (content
      genuinely needs more room), which keeps "saved layouts never clip" - the reason
      auto-height exists - while shrinking stays possible right up to the content's
      true size, where clip detection pushes back.

  frontend/components/charts/chart-card.tsx
      ChartCard distributes the height it now receives: header fixed, content flex-1
      and vertically centred. A fixed-height chart sits in the middle of its card
      instead of leaving all the slack at the bottom, so side-by-side cards read as
      level even when their contents differ.

Run scripts/beautify-overview-motion.py FIRST - this anchors on the wrapper line that
script produces (the deploy order does this).

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
Frontend rebuild required; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

GRID = Path("frontend/components/overview/dashboard-grid.tsx")
CHART_CARD = Path("frontend/components/charts/chart-card.tsx")

# ── dashboard-grid.tsx ────────────────────────────────────────────────────────
MEASURE_ANCHOR = """    const report = () => onMeasure(id, el.offsetHeight);
    const observer = new ResizeObserver(report);
    observer.observe(el);
    report();
    return () => observer.disconnect();
"""
MEASURE_NEW = """    // The wrapper is STRETCHED to its grid cell (below), so offsetHeight reads the
    // CELL, not the content - reporting that would pin minH to the cell's current
    // height and the editor could never shrink a widget again. Report only when the
    // content is actually CLIPPING (scrollHeight exceeds the box): auto-height still
    // grows any cell whose content needs more room - its whole purpose - while
    // shrinking stays possible right up to the content's true size.
    const report = () => {
      if (el.scrollHeight > el.clientHeight + 1) onMeasure(id, el.scrollHeight);
    };
    const observer = new ResizeObserver(report);
    observer.observe(el);
    report();
    return () => observer.disconnect();
"""

WRAPPER_ANCHOR = '    <div ref={ref} className={editable ? "anim-rise pointer-events-none select-none" : "anim-rise"}>\n'
WRAPPER_NEW = '    <div ref={ref} className={editable ? "anim-rise h-full [&>*]:h-full pointer-events-none select-none" : "anim-rise h-full [&>*]:h-full"}>\n'

# ── chart-card.tsx ────────────────────────────────────────────────────────────
CC_IMPORT_ANCHOR = '} from "@/components/ui/card";\n'
CC_IMPORT_ADD = 'import { cn } from "@/lib/utils";\n'

CC_CARD_ANCHOR = "    <Card className={className}>\n"
CC_CARD_NEW = '    <Card className={cn("flex h-full flex-col", className)}>\n'

CC_CONTENT_ANCHOR = "      <CardContent>{children}</CardContent>\n"
CC_CONTENT_NEW = """      {/* flex-1 + centred: a fixed-height chart sits in the middle of whatever height
          the grid gives the card, instead of leaving all the slack at the bottom. */}
      <CardContent className="flex min-h-0 flex-1 flex-col justify-center">
        {children}
      </CardContent>
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def require_once(path: Path, text: str, anchor: str) -> None:
    if text.count(anchor) != 1:
        first = anchor.splitlines()[0].strip()
        die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")


def main() -> None:
    for path in (GRID, CHART_CARD):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    grid = GRID.read_text()
    card = CHART_CARD.read_text()

    todo: dict[Path, str] = {}

    if "[&>*]:h-full" in grid:
        print(f"{GRID}: already stretches")
    else:
        require_once(GRID, grid, MEASURE_ANCHOR)
        require_once(GRID, grid, WRAPPER_ANCHOR)
        text = grid.replace(MEASURE_ANCHOR, MEASURE_NEW, 1)
        text = text.replace(WRAPPER_ANCHOR, WRAPPER_NEW, 1)
        todo[GRID] = text

    if "flex h-full flex-col" in card:
        print(f"{CHART_CARD}: already distributes")
    else:
        for anchor in (CC_IMPORT_ANCHOR, CC_CARD_ANCHOR, CC_CONTENT_ANCHOR):
            require_once(CHART_CARD, card, anchor)
        text = card.replace(CC_IMPORT_ANCHOR, CC_IMPORT_ANCHOR + CC_IMPORT_ADD, 1)
        text = text.replace(CC_CARD_ANCHOR, CC_CARD_NEW, 1)
        text = text.replace(CC_CONTENT_ANCHOR, CC_CONTENT_NEW, 1)
        todo[CHART_CARD] = text

    if not todo:
        print("already level - nothing to do")
        return

    for path, text in todo.items():
        path.write_text(text)
        print(f"patched {path}")

    print("\nRebuild the frontend: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()

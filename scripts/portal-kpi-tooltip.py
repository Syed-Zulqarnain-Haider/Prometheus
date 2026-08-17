#!/usr/bin/env python3
"""Lift the KPI card's tooltip out of the card, into the document body.

The themed tooltip added by ``beautify-kpi-tooltip.py`` is absolutely positioned INSIDE
the card, and the card clips its contents (``overflow-hidden``, so the sparkline respects
the rounded corners). The result on screen: the bubble is sliced off at the card edge and
what survives sits on top of the value and delta underneath it. Styling the bubble was
never going to fix that - an absolutely-positioned child cannot escape an ancestor that
clips.

So the bubble moves to a portal. ``InfoTooltip`` (frontend/components/ui/info-tooltip.tsx)
measures the icon with ``getBoundingClientRect()``, renders into ``document.body`` with
``position: fixed``, and clamps itself to the viewport so the leftmost and rightmost cards
push it inward instead of off-screen. Being fixed to the viewport, a scroll invalidates
the measurement, so it closes on scroll rather than drifting away from its icon.

This patch is only the swap: the whole inline block becomes one line. Everything the old
block did for accessibility - keyboard focus, ``aria-label``, ``pointer-events-none`` -
lives in the component now.

Anchored: the block must appear EXACTLY once, byte for byte as beautify-kpi-tooltip.py
wrote it, or nothing is written. Idempotent. Frontend rebuild required; no migration.

Requires frontend/components/ui/info-tooltip.tsx to be checked out first.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CARD = Path("frontend/components/overview/kpi-card.tsx")
COMPONENT = Path("frontend/components/ui/info-tooltip.tsx")

# Verbatim output of beautify-kpi-tooltip.py - the current state of the file.
ANCHOR = """          {description && (
            <span
              tabIndex={0}
              aria-label={description}
              className="group relative mt-0.5 shrink-0 cursor-help text-muted-foreground/70 outline-none transition-colors hover:text-muted-foreground focus-visible:text-muted-foreground"
            >
              <Info className="h-3.5 w-3.5" />
              {/* Themed tooltip. Anchored to the icon's RIGHT edge because the icon sits
                  at the card's right edge - a left anchor runs off-screen on the last
                  card in the row. */}
              <span
                role="tooltip"
                className="pointer-events-none absolute bottom-full right-0 z-30 mb-2 w-56 rounded-[var(--radius-inner)] border border-[color:var(--color-border)] bg-card px-3 py-2 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
              >
                {description}
                {/* The pointer: a rotated square sharing the bubble's border, with the
                    top-left edges hidden so it reads as a triangle under the bubble. */}
                <span
                  aria-hidden
                  className="absolute -bottom-1 right-2 h-2 w-2 rotate-45 border-b border-r border-[color:var(--color-border)] bg-card"
                />
              </span>
            </span>
          )}
"""

REPLACEMENT = """          {/* Portalled into <body> - the card clips its contents, so a tooltip
              rendered here is cut off at the card edge. */}
          {description && <InfoTooltip text={description} />}
"""

IMPORT_LINE = 'import { InfoTooltip } from "@/components/ui/info-tooltip";\n'
# Inserted before this one: "info-tooltip" sorts ahead of "skeleton", keeping the
# import block in the order eslint expects.
IMPORT_ANCHOR = 'import { Skeleton } from "@/components/ui/skeleton";\n'

LUCIDE_RE = re.compile(r'^import \{([^}]*)\} from "lucide-react";\n', re.M)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def drop_info_import(text: str) -> str:
    """Remove the now-unused ``Info`` icon from the lucide import.

    The icon itself moved into InfoTooltip, so leaving the import behind is an eslint
    error on a clean build. Other icons in the same statement are preserved; if ``Info``
    was the only one, the statement goes entirely.
    """
    if re.search(r"\bInfo\b(?!Tooltip)", text) is None:
        return text  # nothing referencing it - nothing to strip
    match = LUCIDE_RE.search(text)
    if match is None:
        # Info is referenced but not imported from lucide-react: the file is not the
        # shape this patch expects, so leave the import alone rather than guess.
        return text
    names = [n.strip() for n in match.group(1).split(",") if n.strip()]
    remaining = [n for n in names if n != "Info"]
    if remaining == names:
        return text
    if not remaining:
        before, after = text[: match.start()], text[match.end() :]
        # The statement stood alone in its own import group; removing it would leave a
        # double blank line behind.
        if before.endswith("\n\n") and after.startswith("\n"):
            after = after[1:]
        return before + after
    kept = 'import { ' + ", ".join(remaining) + ' } from "lucide-react";\n'
    return text[: match.start()] + kept + text[match.end() :]


def main() -> None:
    if not CARD.exists():
        die(f"{CARD} not found - run from the repository root")
    if not COMPONENT.exists():
        die(f"{COMPONENT} not found - check it out before running this patch")

    text = CARD.read_text()

    if "InfoTooltip" in text:
        print("already portalled - nothing to do")
        return
    if text.count(ANCHOR) != 1:
        die(
            f"{CARD}: expected exactly one inline tooltip block, found {text.count(ANCHOR)} - "
            "the component has changed shape, patch it by hand"
        )
    if text.count(IMPORT_ANCHOR) != 1:
        die(f"{CARD}: expected exactly one {IMPORT_ANCHOR.strip()!r}")

    text = text.replace(ANCHOR, REPLACEMENT, 1)
    text = text.replace(IMPORT_ANCHOR, IMPORT_LINE + IMPORT_ANCHOR, 1)
    text = drop_info_import(text)

    CARD.write_text(text)
    print(f"patched {CARD}: tooltip now renders in a portal, outside the card's clipping")
    print("\nRebuild the frontend: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()

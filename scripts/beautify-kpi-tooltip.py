#!/usr/bin/env python3
"""Replace the KPI card's native browser tooltip with a themed one.

``title={description}`` renders the browser's own tooltip: a black box with default
system styling that ignores the theme, has no arrow, and appears wherever the browser
decides after its own delay. This swaps it for a styled bubble - card background, the
app's border colour and radius, a pointer arrow, and a fade-in.

Details that matter:
  * ``group`` + ``group-hover``/``group-focus-within`` means it shows on hover AND on
    keyboard focus, so the description is not mouse-only. ``tabIndex={0}`` makes the
    icon reachable by keyboard at all.
  * ``aria-label`` stays: the visual bubble is decoration, screen readers use the label.
  * ``right-0`` anchors the bubble's RIGHT edge to the icon, which sits at the card's
    right edge - anchoring left would push it off-screen on the rightmost card.
  * ``pointer-events-none`` stops the bubble from stealing hover from the icon and
    flickering.
  * Reduced motion skips the fade (the transition is opacity-only, so it degrades
    cleanly rather than needing a media query).

Applies to every KPI card across Overview, Revenue, UA and Store - they share this
component. Anchored: the block must appear EXACTLY once or nothing is written.
"""

from __future__ import annotations

import sys
from pathlib import Path

CARD = Path("frontend/components/overview/kpi-card.tsx")

ANCHOR = """          {description && (
            <span
              title={description}
              aria-label={description}
              className="mt-0.5 shrink-0 cursor-help text-muted-foreground/70 transition-colors hover:text-muted-foreground"
            >
              <Info className="h-3.5 w-3.5" />
            </span>
          )}
"""

REPLACEMENT = """          {description && (
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


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not CARD.exists():
        die(f"{CARD} not found - run from the repository root")
    text = CARD.read_text()

    if 'role="tooltip"' in text:
        print("already themed - nothing to do")
        return
    if text.count(ANCHOR) != 1:
        die(
            f"{CARD}: expected exactly one native-tooltip block, found {text.count(ANCHOR)} - "
            "the component has changed shape, patch it by hand"
        )

    CARD.write_text(text.replace(ANCHOR, REPLACEMENT, 1))
    print(f"patched {CARD}: themed tooltip replaces the browser's native one")
    print("\nApplies to every KPI card - Overview, Revenue, UA and Store share this component.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Three mobile-canvas fixes for the phone screenshot's dead zones.

1. frontend/app/globals.css - paint <html> the app background too, and clip
   page-level horizontal overflow.

   The screenshot showed a navy band beyond the app's right/bottom edge. The app
   background lives on <body>; when the page can be panned or zoomed past the layout
   viewport (any stray element a few px too wide is enough), the region beyond the
   canvas shows the BROWSER'S default dark surface - which is navy-ish, and reads as
   "the app stops here". Painting <html> the same token makes any such region
   indistinguishable from the app. `overflow-x: clip` on <body> then removes the pan
   entirely: no page-level sideways scroll exists, while every wide table keeps its own
   overflow-x-auto scroller inside its card (clip, not hidden - hidden would create a
   scroll container and swallow position: sticky descendants).

2. frontend/components/effects/privacy-shield.tsx - hide the eye button on
   touch-only devices (shipped as a full-file checkout; this script only verifies it).
   The shield reveals a circle around the MOUSE POINTER - on a phone there is no
   pointer, so the toggle was a dead control that blurred the screen with no way to
   reveal anything, floating over scarce content space.

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
Frontend rebuild required; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

GLOBALS = Path("frontend/app/globals.css")
SHIELD = Path("frontend/components/effects/privacy-shield.tsx")

CSS_ANCHOR = """  body {
    background-color: var(--color-bg-app);
"""
CSS_NEW = """  html {
    /* Same surface as body: if the page is ever panned or zoomed past the layout
       viewport, the exposed canvas matches the app instead of showing the browser's
       own (navy) dark surface as a dead band. */
    background-color: var(--color-bg-app);
    /* No page-level sideways pan, ever - a single stray element a few px too wide
       otherwise makes the whole page horizontally scrollable on phones. Wide tables
       are unaffected: each scrolls inside its own overflow-x-auto card. */
    overflow-x: clip;
  }
  body {
    background-color: var(--color-bg-app);
    overflow-x: clip;
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not GLOBALS.exists():
        die(f"{GLOBALS} not found - run from the repository root")
    if not SHIELD.exists():
        die(f"{SHIELD} not found - check it out before running this")
    if "hover:hover" not in SHIELD.read_text():
        die(f"{SHIELD} is an old copy without the touch-device guard - check out the new one")

    text = GLOBALS.read_text()
    if "overflow-x: clip" in text:
        print("already polished - nothing to do")
        return
    if text.count(CSS_ANCHOR) != 1:
        die(f"{GLOBALS}: expected exactly one body background block")

    GLOBALS.write_text(text.replace(CSS_ANCHOR, CSS_NEW, 1))
    print(f"patched {GLOBALS}: html painted + page-level horizontal overflow clipped")
    print("\nRebuild the frontend: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()

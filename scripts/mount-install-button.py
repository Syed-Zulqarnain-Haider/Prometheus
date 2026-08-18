#!/usr/bin/env python3
"""Mount the "Install app" button in the header.

``components/pwa/install-app-button.tsx`` is checked out alongside this script. The
header is where it belongs: visible on every page at every width, and the component
hides itself wherever installing is impossible or already done, so on desktop browsers
without install support the header is unchanged.

It goes FIRST in the header's right-hand cluster, before the user's email - a promo
for a capability sits ahead of identity chrome, and on phones (where it matters most)
the email is hidden anyway so the button leads the row.

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
Frontend rebuild required; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

HEADER = Path("frontend/components/layout/header.tsx")
BUTTON = Path("frontend/components/pwa/install-app-button.tsx")

IMPORT_ANCHOR = 'import { MobileNav } from "@/components/layout/mobile-nav";\n'
IMPORT_ADD = 'import { InstallAppButton } from "@/components/pwa/install-app-button";\n'

MOUNT_ANCHOR = '      <div className="ml-auto flex items-center gap-1 sm:gap-2">\n'
MOUNT_NEW = """      <div className="ml-auto flex items-center gap-1 sm:gap-2">
        {/* Renders nothing when the app is already installed or the browser offers no
            install path - never a dead control. */}
        <InstallAppButton />
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not HEADER.exists():
        die(f"{HEADER} not found - run from the repository root")
    if not BUTTON.exists():
        die(f"{BUTTON} not found - check it out before running this")

    text = HEADER.read_text()
    if "InstallAppButton" in text:
        print("already mounted - nothing to do")
        return

    for anchor in (IMPORT_ANCHOR, MOUNT_ANCHOR):
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{HEADER}: expected exactly one {first!r}, found {text.count(anchor)}")

    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_ADD, 1)
    text = text.replace(MOUNT_ANCHOR, MOUNT_NEW, 1)
    HEADER.write_text(text)
    print(f"patched {HEADER}: Install app button mounted")
    print("\nRebuild the frontend: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()

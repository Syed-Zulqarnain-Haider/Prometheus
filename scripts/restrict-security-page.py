#!/usr/bin/env python3
"""Make the Security page admin-only (owner request).

Adds ``requiresAdmin: true`` to the /security nav entry, so the sidebar and mobile nav
hide it from every non-admin - the sidebar already filters on that flag.

NOTE: this is the MENU half only. Hiding a link is cosmetic: a non-admin can still type
/security into the address bar. The page itself needs a guard too (added separately once
its component has been read). Never treat nav filtering as access control.

Anchored: the nav line must appear EXACTLY once or nothing is written. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

NAV = Path("frontend/lib/nav.ts")
ANCHOR = '  { href: "/security", label: "Security", icon: ShieldCheck },\n'
REPLACEMENT = (
    '  { href: "/security", label: "Security", icon: ShieldCheck, requiresAdmin: true },\n'
)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not NAV.exists():
        die(f"{NAV} not found - run from the repository root")
    text = NAV.read_text()

    if '"/security", label: "Security", icon: ShieldCheck, requiresAdmin: true' in text:
        print("already admin-only - nothing to do")
        return
    if text.count(ANCHOR) != 1:
        die(
            f"{NAV}: expected exactly one {ANCHOR.strip()!r}, found {text.count(ANCHOR)}. "
            "The nav entry has changed shape - check it by hand."
        )

    NAV.write_text(text.replace(ANCHOR, REPLACEMENT, 1))
    print(f"patched {NAV}: /security is now requiresAdmin")
    print("\nMENU ONLY. The page still answers a direct /security URL until its component")
    print("carries a guard as well - that is the part that actually restricts access.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Add the Chat/Profile/Spotlight nav entries and mount the header presence menu.

The pages, the sidebar grouping, and the presence-menu component are already delivered;
this script makes the two SERVER-OWNED files aware of them:

  frontend/lib/nav.ts                    - three NAV_ITEMS entries + their lucide imports
  frontend/components/layout/header.tsx  - import + mount <PresenceMenu /> ("who is active")

Anchored patch, not an overwrite: every anchor must appear EXACTLY once or the script
aborts without writing anything. Idempotent - a second run is a no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path

NAV = Path("frontend/lib/nav.ts")
HEADER = Path("frontend/components/layout/header.tsx")


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


# (anchor, insertion-after-anchor) pairs. Icon imports keep the block alphabetical
# (Megaphone < MessageCircle, ShieldCheck < Sparkles, Store < User).
NAV_EDITS: list[tuple[str, str]] = [
    ("  Megaphone,\n", "  MessageCircle,\n"),
    ("  ShieldCheck,\n", "  Sparkles,\n"),
    ("  Store,\n", "  User,\n"),
    (
        '  { href: "/glossary", label: "Glossary", icon: BookOpen },\n',
        '  { href: "/spotlight", label: "Spotlight", icon: Sparkles },\n'
        '  { href: "/chat", label: "Chat", icon: MessageCircle },\n'
        '  { href: "/profile", label: "Profile", icon: User },\n',
    ),
]

HEADER_IMPORT_ANCHOR = 'import { NotificationBell } from "@/components/layout/notification-bell";\n'
HEADER_IMPORT_ADD = 'import { PresenceMenu } from "@/components/layout/presence-menu";\n'
HEADER_MOUNT_ANCHOR = '        <span data-tour="notifications">\n'
HEADER_MOUNT_ADD = "        <PresenceMenu />\n"


def patch_nav(text: str) -> str | None:
    if '"/chat"' in text:
        return None  # already patched
    for anchor, _ in NAV_EDITS:
        if text.count(anchor) != 1:
            die(f"{NAV}: expected exactly one {anchor.strip()!r}, found {text.count(anchor)}")
    for anchor, insertion in NAV_EDITS:
        text = text.replace(anchor, anchor + insertion, 1)
    return text


def patch_header(text: str) -> str | None:
    if "PresenceMenu" in text:
        return None  # already patched
    for anchor in (HEADER_IMPORT_ANCHOR, HEADER_MOUNT_ANCHOR):
        if text.count(anchor) != 1:
            die(f"{HEADER}: expected exactly one {anchor.strip()!r}, found {text.count(anchor)}")
    text = text.replace(HEADER_IMPORT_ANCHOR, HEADER_IMPORT_ANCHOR + HEADER_IMPORT_ADD, 1)
    # The presence menu sits immediately LEFT of the notification bell.
    return text.replace(HEADER_MOUNT_ANCHOR, HEADER_MOUNT_ADD + HEADER_MOUNT_ANCHOR, 1)


def main() -> None:
    for path in (NAV, HEADER):
        if not path.exists():
            die(f"{path} not found - run from the repository root")
    menu = Path("frontend/components/layout/presence-menu.tsx")
    if not menu.exists():
        die(f"{menu} not found - check it out from the dev branch before running this")

    nav_text = patch_nav(NAV.read_text())
    header_text = patch_header(HEADER.read_text())

    if nav_text is None and header_text is None:
        print("Already patched - nothing to do.")
        return
    if nav_text is not None:
        NAV.write_text(nav_text)
        print(f"patched {NAV}: Spotlight/Chat/Profile nav entries added")
    else:
        print(f"{NAV}: already has /chat - left untouched")
    if header_text is not None:
        HEADER.write_text(header_text)
        print(f"patched {HEADER}: PresenceMenu mounted beside the notification bell")
    else:
        print(f"{HEADER}: already mounts PresenceMenu - left untouched")


if __name__ == "__main__":
    main()

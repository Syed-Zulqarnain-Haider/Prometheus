#!/usr/bin/env python3
"""Wire the Chat page and the header presence menu into the DEPLOYED frontend.

The new code ships as whole files (chat page/components, profile page, presence menu, the
hooks). Two deployed files have drifted from this tree and are patched by anchor instead:

  * ``lib/nav.ts``       - add the Chat entry (its icon import alphabetically)
  * ``components/layout/header.tsx`` - mount <PresenceMenu /> beside the notification bell

Every anchor must match exactly once or nothing is written. Re-running is a no-op.

Run from the repository root:  python3 scripts/patch-chat-nav-header.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# (path, already-applied marker, [(anchor, replacement)])
PATCHES: list[tuple[Path, str, list[tuple[str, str]]]] = [
    (
        Path("frontend/lib/nav.ts"),
        '"/chat"',
        [
            ("  Megaphone,\n", "  Megaphone,\n  MessagesSquare,\n"),
            (
                '  { href: "/compare", label: "Compare", icon: Scale },\n',
                '  { href: "/compare", label: "Compare", icon: Scale },\n'
                '  { href: "/chat", label: "Chat", icon: MessagesSquare },\n',
            ),
        ],
    ),
    (
        Path("frontend/components/layout/header.tsx"),
        "PresenceMenu",
        [
            (
                'import { NotificationBell } from "@/components/layout/notification-bell";',
                'import { NotificationBell } from "@/components/layout/notification-bell";\n'
                'import { PresenceMenu } from "@/components/layout/presence-menu";',
            ),
            (
                '        <span data-tour="notifications">',
                "        <PresenceMenu />\n        <span data-tour=\"notifications\">",
            ),
        ],
    ),
    (
        Path("frontend/lib/nav.ts"),
        '"/spotlight"',
        [
            ("  Scale,\n", "  Scale,\n  Sparkles,\n"),
            (
                '  { href: "/chat", label: "Chat", icon: MessagesSquare },\n',
                '  { href: "/chat", label: "Chat", icon: MessagesSquare },\n'
                '  { href: "/spotlight", label: "Spotlight", icon: Sparkles },\n',
            ),
        ],
    ),
]


def main() -> None:
    # Pass 1: verify everything before writing anything.
    todo: list[tuple[Path, list[tuple[str, str]]]] = []
    for path, marker, edits in PATCHES:
        if not path.exists():
            print(f"ABORTED: {path} not found - run from the repository root", file=sys.stderr)
            raise SystemExit(1)
        text = path.read_text()
        if marker in text:
            print(f"skipped  {path} (already patched)")
            continue
        for anchor, _ in edits:
            count = text.count(anchor)
            if count != 1:
                print(
                    f"ABORTED: {path}: anchor matched {count} times, expected 1:\n"
                    f"    {anchor.strip()[:80]}",
                    file=sys.stderr,
                )
                print("Nothing was written.", file=sys.stderr)
                raise SystemExit(1)
        todo.append((path, edits))

    # Pass 2: write.
    for path, edits in todo:
        text = path.read_text()
        for anchor, replacement in edits:
            text = text.replace(anchor, replacement, 1)
        path.write_text(text)
        print(f"patched  {path}")


if __name__ == "__main__":
    main()

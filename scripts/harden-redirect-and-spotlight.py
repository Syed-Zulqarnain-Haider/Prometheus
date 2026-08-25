#!/usr/bin/env python3
"""Close two audit findings: a backslash open-redirect bypass, and the unguarded
Spotlight page.

1. OPEN REDIRECT. Three places allow a link when it ``startswith("/")`` and not
   ``startswith("//")``, on the stated grounds that this admits only in-app paths.
   It does not. Browsers implement the WHATWG URL spec, which treats a backslash as
   equivalent to a forward slash for special schemes, so ``/\\evil.com`` passes both
   tests and then resolves to ``https://evil.com/``. That turns the platform-wide
   announcement banner - rendered for every user - into a one-click off-site redirect,
   and hands ``router.push`` a foreign origin, which it forwards to a full-page
   navigation. Rejecting a backslash outright restores the property the comments
   already claim: a backslash is never legitimate in an in-app path.

2. SPOTLIGHT. ``/spotlight`` edits BigQuery master data through the ADMIN App Master
   API, but carried no capability guard and no ``requiresAdmin`` nav flag - so it sat
   in the sidebar for every role, including viewer. Both halves are needed: hiding the
   nav entry restricts nothing on its own, because a typed URL still renders the page.
   The guard is placed before the data hooks run, so a non-admin never issues the
   admin request at all. This mirrors app-master-client.tsx, which already does exactly
   this with the same two lines.

Two passes: every anchor is verified first, and nothing is written unless all of them
match exactly once. Re-running is a no-op.

Run from the repository root:  python3 scripts/harden-redirect-and-spotlight.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── (path, already-applied marker, [(anchor, replacement)]) ─────────────────────────
PATCHES: list[tuple[Path, str, list[tuple[str, str]]]] = [
    (
        Path("backend/app/api/v1/announcements.py"),
        'if "\\\\" in value',
        [
            (
                '        if value.startswith("/") and not value.startswith("//"):\n'
                "            return value\n",
                "        # A backslash is never legitimate in an in-app path, and browsers follow the\n"
                "        # WHATWG URL rule that treats it as a forward slash for special schemes - so\n"
                '        # "/\\\\evil.com" would pass the two tests below and still resolve off-site.\n'
                '        if "\\\\" in value:\n'
                '            raise ValueError("Link must be an in-app path starting with / or an https:// URL")\n'
                '        if value.startswith("/") and not value.startswith("//"):\n'
                "            return value\n",
            )
        ],
    ),
    (
        Path("frontend/components/layout/announcement-bar.tsx"),
        'url.includes("\\\\")',
        [
            (
                "function safeHref(url: string | null): string | null {\n"
                "  if (!url) return null;\n"
                '  if (url.startsWith("/") && !url.startsWith("//")) return url;\n',
                "function safeHref(url: string | null): string | null {\n"
                "  if (!url) return null;\n"
                "  // Browsers treat a backslash as a forward slash for special schemes, so\n"
                '  // "/\\\\evil.com" passes the leading-slash test below and still lands off-site.\n'
                '  if (url.includes("\\\\")) return null;\n'
                '  if (url.startsWith("/") && !url.startsWith("//")) return url;\n',
            )
        ],
    ),
    (
        Path("frontend/components/layout/notification-bell.tsx"),
        '!n.link.includes("\\\\")',
        [
            (
                '    if (n.link && n.link.startsWith("/") && !n.link.startsWith("//")) {\n',
                "    // The backslash test matters: browsers resolve a backslash as a forward slash\n"
                '    // for special schemes, so "/\\\\evil.com" satisfies both slash tests and then\n'
                "    // reaches router.push() as a foreign origin.\n"
                "    if (\n"
                "      n.link &&\n"
                '      n.link.startsWith("/") &&\n'
                '      !n.link.startsWith("//") &&\n'
                '      !n.link.includes("\\\\")\n'
                "    ) {\n",
            )
        ],
    ),
    (
        Path("frontend/lib/nav.ts"),
        '{ href: "/spotlight", label: "Spotlight", icon: Sparkles, requiresAdmin: true }',
        [
            (
                '  { href: "/spotlight", label: "Spotlight", icon: Sparkles },',
                '  { href: "/spotlight", label: "Spotlight", icon: Sparkles, requiresAdmin: true },',
            )
        ],
    ),
    (
        Path("frontend/components/spotlight/spotlight-client.tsx"),
        "admin_panel",
        [
            (
                "import {\n"
                "  type AppMasterFilters,\n"
                "  useAppMaster,\n"
                "  useUpdateAppMaster,\n"
                '} from "@/lib/api-hooks";',
                "import {\n"
                "  type AppMasterFilters,\n"
                "  useAppMaster,\n"
                "  useMe,\n"
                "  useUpdateAppMaster,\n"
                '} from "@/lib/api-hooks";',
            ),
            (
                "export function SpotlightClient() {\n"
                "  const list = useAppMaster(EMPTY_FILTERS, PAGE, 0);\n",
                "export function SpotlightClient() {\n"
                "  const { data: me, isLoading: meLoading } = useMe();\n"
                "  const list = useAppMaster(EMPTY_FILTERS, PAGE, 0);\n",
            ),
            (
                "  if (list.isLoading) {\n"
                '    return <p className="text-sm text-muted-foreground">Loading app master...</p>;\n'
                "  }\n",
                "  // Spotlight edits master data through the ADMIN App Master API, so it carries the\n"
                "  // same guard app-master-client.tsx does. Hiding the nav entry restricts nothing on\n"
                "  // its own - a typed /spotlight URL still renders this component. Placed after every\n"
                "  // hook, so the early return cannot change hook order between renders.\n"
                "  if (meLoading) {\n"
                '    return <p className="text-sm text-muted-foreground">Loading...</p>;\n'
                "  }\n"
                '  if (!me?.capabilities.includes("admin_panel")) {\n'
                '    return <p className="text-sm text-muted-foreground">You don&apos;t have access to Spotlight.</p>;\n'
                "  }\n"
                "  if (list.isLoading) {\n"
                '    return <p className="text-sm text-muted-foreground">Loading app master...</p>;\n'
                "  }\n",
            ),
        ],
    ),
]


def die(message: str) -> None:
    print(f"ABORT: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    # ── Pass 1: verify everything ───────────────────────────────────────────────
    todo: list[tuple[Path, list[tuple[str, str]]]] = []
    for path, marker, edits in PATCHES:
        if not path.exists():
            die(f"{path} not found")
        text = path.read_text()
        if marker in text:
            print(f"skipped  {path} (already patched)")
            continue
        for anchor, _ in edits:
            count = text.count(anchor)
            if count != 1:
                die(f"{path}: anchor matched {count} times, expected 1:\n    {anchor[:90]}...")
        todo.append((path, edits))

    if not todo:
        print("\nNothing to do - every patch is already applied.")
        return

    # ── Pass 2: write ───────────────────────────────────────────────────────────
    for path, edits in todo:
        text = path.read_text()
        for anchor, replacement in edits:
            text = text.replace(anchor, replacement, 1)
        path.write_text(text)
        print(f"patched  {path}")

    print("\nNext: rebuild and restart, after the import smoke test:")
    print("  docker compose -f docker-compose.prod.yml run --rm backend python -c 'import app.main'")
    print("  docker compose -f docker-compose.prod.yml up -d --build backend frontend")


if __name__ == "__main__":
    main()

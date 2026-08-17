#!/usr/bin/env python3
"""Wire up the installable mobile app: viewport, service worker, and phone navigation.

Three small edits to files that already exist. Everything else the mobile app needs
(manifest, icons, offline page, service worker, drawer component) is new files checked
out alongside this script.

  frontend/app/layout.tsx
      * `export const viewport` - THE mobile fix. Without a viewport meta tag a phone
        renders the page at ~980px wide and scales it down, which is why the dashboard
        looked like a shrunken desktop rather than a mobile layout: none of the
        responsive breakpoints ever fired, because the browser reported a desktop width.
        `viewportFit: "cover"` lets the app paint under the notch; the safe-area insets
        in the components keep content out from under it.
      * `themeColor` - tints the Android status bar and the iOS standalone header to the
        app surface instead of leaving a white band above the dark UI.
      * `<ServiceWorkerRegister />` - registers /sw.js, which is what makes the browser
        offer "Install app" at all.

  frontend/app/(app)/layout.tsx
      Page padding drops from a flat p-6 to p-4 on phones, and gains the bottom safe-area
      inset so the last row of a table is not sitting under the iPhone home indicator.

  frontend/components/layout/sidebar.tsx
      NOT touched (an earlier revision mounted <MobileNav /> here; the deployed header
      already mounts it in its own flex row, where it takes real space beside the brand
      instead of floating over it). If an earlier run of this script added the sidebar
      mount, it is REMOVED so the drawer never renders twice.

Anchored: every anchor must appear EXACTLY once in each file or NOTHING is written -
all three files are validated before any is touched, because a viewport tag without the
drawer (or the reverse) is a worse state than either. Idempotent. Frontend rebuild
required; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_LAYOUT = Path("frontend/app/layout.tsx")
APP_LAYOUT = Path("frontend/app/(app)/layout.tsx")
SIDEBAR = Path("frontend/components/layout/sidebar.tsx")
MOBILE_NAV = Path("frontend/components/layout/mobile-nav.tsx")
SW_REGISTER = Path("frontend/components/pwa/service-worker-register.tsx")
# The register component 404s silently if these are missing, and "Install app" never
# appears with no error anywhere - so their absence must abort the run instead.
PWA_ASSETS = (
    Path("frontend/app/manifest.ts"),
    Path("frontend/public/sw.js"),
    Path("frontend/public/offline.html"),
    Path("frontend/public/icon-192.png"),
    Path("frontend/public/icon-512.png"),
    Path("frontend/public/icon-maskable-512.png"),
    Path("frontend/public/apple-touch-icon.png"),
)

# ── frontend/app/layout.tsx ────────────────────────────────────────────────────
ROOT_TYPE_ANCHOR = 'import type { Metadata } from "next";\n'
ROOT_TYPE_NEW = 'import type { Metadata, Viewport } from "next";\n'

ROOT_IMPORT_ANCHOR = 'import { Providers } from "@/app/providers";\n'
ROOT_IMPORT_ADD = (
    'import { ServiceWorkerRegister } from "@/components/pwa/service-worker-register";\n'
)

ROOT_VIEWPORT_ANCHOR = "export default function RootLayout({\n"
ROOT_VIEWPORT_ADD = '''/* Without this a phone assumes a ~980px desktop viewport and scales the whole page down,
 * so every responsive breakpoint in the app measures the wrong width and never fires.
 * This is what makes the mobile layout actually be a mobile layout.
 *
 * userScalable stays ON: pinch-zoom is an accessibility feature, and locking it away to
 * make an app feel "native" is not a trade worth making on a dashboard full of figures. */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Paint under the notch; the safe-area insets in the shell keep content clear of it.
  viewportFit: "cover",
  themeColor: "#0b0b0d",
};

'''

ROOT_MOUNT_ANCHOR = "        <Providers>{children}</Providers>\n"
ROOT_MOUNT_NEW = """        <Providers>{children}</Providers>
        <ServiceWorkerRegister />
"""

# ── frontend/app/(app)/layout.tsx ──────────────────────────────────────────────
# Two forms are in the wild: the original flat p-6, and a p-4 sm:p-6 that a previous pass
# already applied. Either is a valid starting point and both end at the same place, so the
# patch accepts whichever it finds rather than aborting the whole run on the tidier one.
MAIN_ANCHORS = (
    '        <main className="flex-1 overflow-auto p-6">{children}</main>\n',
    '        <main className="flex-1 overflow-auto p-4 sm:p-6">{children}</main>\n',
)
MAIN_NEW = """        {/* Tighter padding on phones - 24px of chrome on a 360px screen is 13% of the
            width. The bottom inset keeps the last row clear of the iPhone home indicator. */}
        <main
          className="flex-1 overflow-auto p-4 sm:p-6"
          style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom, 0px))" }}
        >
          {children}
        </main>
"""

# ── frontend/components/layout/sidebar.tsx ─────────────────────────────────────
# The header mounts <MobileNav /> already; an earlier revision of this script also
# mounted it in the sidebar, which would render two hamburgers. These are the exact
# lines that revision added - if present, they are stripped.
SIDEBAR_STALE_IMPORT = 'import { MobileNav } from "@/components/layout/mobile-nav";\n'
SIDEBAR_STALE_MOUNT = """    {/* The sidebar below is `hidden md:block`; this is its counterpart under that
        breakpoint, so navigation exists at every width. */}
    <MobileNav />
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def require_once(path: Path, text: str, anchor: str) -> None:
    if text.count(anchor) != 1:
        die(f"{path}: expected exactly one {anchor.strip()!r}, found {text.count(anchor)}")


def main() -> None:
    for path in (ROOT_LAYOUT, APP_LAYOUT, SIDEBAR):
        if not path.exists():
            die(f"{path} not found - run from the repository root")
    for path in (MOBILE_NAV, SW_REGISTER, *PWA_ASSETS):
        if not path.exists():
            die(f"{path} not found - check the new files out before running this")

    root = ROOT_LAYOUT.read_text()
    app = APP_LAYOUT.read_text()
    sidebar = SIDEBAR.read_text()

    todo: dict[Path, str] = {}

    # ── validate everything before writing anything ──
    if "ServiceWorkerRegister" in root:
        print(f"{ROOT_LAYOUT}: already wired")
    else:
        for anchor in (ROOT_TYPE_ANCHOR, ROOT_IMPORT_ANCHOR, ROOT_VIEWPORT_ANCHOR, ROOT_MOUNT_ANCHOR):
            require_once(ROOT_LAYOUT, root, anchor)
        if "export const viewport" in root:
            die(f"{ROOT_LAYOUT}: a viewport export already exists - merge by hand")
        todo[ROOT_LAYOUT] = root

    main_anchor: str | None = None
    if "safe-area-inset-bottom" in app:
        print(f"{APP_LAYOUT}: already responsive")
    else:
        found = [anchor for anchor in MAIN_ANCHORS if app.count(anchor) == 1]
        if len(found) != 1:
            die(
                f"{APP_LAYOUT}: expected exactly one known <main> line, matched {len(found)} - "
                "the layout has changed shape, patch it by hand"
            )
        main_anchor = found[0]
        todo[APP_LAYOUT] = app

    # The header owns the mount; strip the sidebar mount if an earlier run added it.
    if SIDEBAR_STALE_IMPORT in sidebar or SIDEBAR_STALE_MOUNT in sidebar:
        todo[SIDEBAR] = sidebar
    else:
        print(f"{SIDEBAR}: clean (header owns the drawer mount)")

    if not todo:
        print("already wired - nothing to do")
        return

    # ── write ──
    if ROOT_LAYOUT in todo:
        text = todo[ROOT_LAYOUT]
        text = text.replace(ROOT_TYPE_ANCHOR, ROOT_TYPE_NEW, 1)
        text = text.replace(ROOT_IMPORT_ANCHOR, ROOT_IMPORT_ANCHOR + ROOT_IMPORT_ADD, 1)
        text = text.replace(ROOT_VIEWPORT_ANCHOR, ROOT_VIEWPORT_ADD + ROOT_VIEWPORT_ANCHOR, 1)
        text = text.replace(ROOT_MOUNT_ANCHOR, ROOT_MOUNT_NEW, 1)
        ROOT_LAYOUT.write_text(text)
        print(f"patched {ROOT_LAYOUT}: viewport + theme colour + service worker")

    if APP_LAYOUT in todo and main_anchor is not None:
        APP_LAYOUT.write_text(todo[APP_LAYOUT].replace(main_anchor, MAIN_NEW, 1))
        print(f"patched {APP_LAYOUT}: responsive page padding + safe area")

    if SIDEBAR in todo:
        text = todo[SIDEBAR]
        text = text.replace(SIDEBAR_STALE_IMPORT, "", 1)
        text = text.replace(SIDEBAR_STALE_MOUNT, "", 1)
        SIDEBAR.write_text(text)
        print(f"patched {SIDEBAR}: removed the duplicate drawer mount")

    print("\nThe app is now installable: open it on the phone and use 'Add to Home Screen'.")
    print("Rebuild: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()

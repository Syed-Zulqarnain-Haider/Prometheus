#!/usr/bin/env python3
"""Three input-hardening fixes from the frontend audit.

1. lib/filters.ts - VALIDATE the from/to dates taken from the URL.
   parseFilters trusted them verbatim, and previousWindow() runs them through
   date-fns format(), which THROWS on an invalid date. previousWindow is called
   unconditionally during render (the app tape, usePreviousTimeseries), so anyone
   opening a shared link with `?from=x` - one mistyped character - took down the
   whole page behind the route error boundary. Malformed dates now fall back to
   the preset range, same as an unknown preset already did.

2. components/reports/saved-views-menu.tsx - MERGE saved filters over defaults.
   Views saved before newer filter fields existed (podOwners, consoles, ...) lack
   those keys; filtersToParams dereferences `.length` on them, so applying an old
   view threw inside the click handler and silently did nothing. Merging over
   defaultFilters() gives every missing key its empty default and old views apply
   cleanly.

3. components/layout/notification-bell.tsx - allow-list notification deep-links.
   Announcements already run their CTA through safeHref() as a second line of
   defence; notification links did router.push(n.link) on the server-supplied
   string unguarded. Same trust level, same guard: relative paths only (the model
   only ever produces in-app links), anything else is ignored.

Anchored: every anchor must appear EXACTLY once in its file or NOTHING is
written - all files validate before any is touched. Idempotent. Frontend
rebuild required; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

FILTERS = Path("frontend/lib/filters.ts")
VIEWS = Path("frontend/components/reports/saved-views-menu.tsx")
BELL = Path("frontend/components/layout/notification-bell.tsx")

# ── 1. filters.ts ─────────────────────────────────────────────────────────────
FILTERS_HELPER_ANCHOR = "export function parseFilters(params: URLSearchParams): Filters {\n"
FILTERS_HELPER_ADD = '''/** A URL date is used only if it is a real calendar date. Anything else falls back -
 *  previousWindow() runs these through date-fns format(), which THROWS on an invalid
 *  date, so one mistyped character in a shared link crashed the whole page. */
function safeDate(raw: string | null, fallback: string): string {
  if (!raw || !/^\\d{4}-\\d{2}-\\d{2}$/.test(raw)) return fallback;
  // Round-trip, because Date ROLLS impossible days (2026-02-30 becomes March 2) while
  // date-fns parseISO rejects them - so a rolled date would still crash format() later.
  const parsed = new Date(`${raw}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return fallback;
  return parsed.toISOString().slice(0, 10) === raw ? raw : fallback;
}

'''

FILTERS_USE_ANCHOR = """    dateFrom: params.get("from") ?? base.dateFrom,
    dateTo: params.get("to") ?? base.dateTo,
"""
FILTERS_USE_NEW = """    dateFrom: safeDate(params.get("from"), base.dateFrom),
    dateTo: safeDate(params.get("to"), base.dateTo),
"""

# ── 2. saved-views-menu.tsx ───────────────────────────────────────────────────
VIEWS_ANCHOR = """                    onClick={() => {
                      setFilters(view.filters as unknown as Filters);
                      setOpen(false);
                    }}
"""
VIEWS_NEW = """                    onClick={() => {
                      // Merge over defaults: views saved before newer filter fields
                      // existed lack those keys, and filtersToParams dereferences
                      // them - applying an old view used to throw and do nothing.
                      setFilters({
                        ...defaultFilters(),
                        ...(view.filters as unknown as Partial<Filters>),
                      });
                      setOpen(false);
                    }}
"""

# The file imports the Filters type already; defaultFilters rides on that import.
VIEWS_IMPORT_ANCHORS = (
    'import type { Filters } from "@/lib/filters";\n',
    'import { type Filters } from "@/lib/filters";\n',
)
VIEWS_IMPORT_NEW = 'import { defaultFilters, type Filters } from "@/lib/filters";\n'

# ── 3. notification-bell.tsx ──────────────────────────────────────────────────
BELL_ANCHOR = """    if (n.link) {
      setOpen(false);
      router.push(n.link); // deep-link straight to where the change happened
    }
"""
BELL_NEW = """    // Relative in-app paths only - the same second-line guard announcements apply
    // to their CTA. The server only ever writes in-app links, so anything else
    // here is a bug or tampering, and ignoring it beats navigating to it.
    if (n.link && n.link.startsWith("/") && !n.link.startsWith("//")) {
      setOpen(false);
      router.push(n.link); // deep-link straight to where the change happened
    }
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
    for path in (FILTERS, VIEWS, BELL):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    filters = FILTERS.read_text()
    views = VIEWS.read_text()
    bell = BELL.read_text()

    todo: dict[Path, str] = {}

    if "function safeDate" in filters:
        print(f"{FILTERS}: already validated")
    else:
        require_once(FILTERS, filters, FILTERS_HELPER_ANCHOR)
        require_once(FILTERS, filters, FILTERS_USE_ANCHOR)
        todo[FILTERS] = filters

    views_import: str | None = None
    if "defaultFilters()" in views:
        print(f"{VIEWS}: already merges defaults")
    else:
        require_once(VIEWS, views, VIEWS_ANCHOR)
        found = [a for a in VIEWS_IMPORT_ANCHORS if views.count(a) == 1]
        if len(found) != 1:
            die(f"{VIEWS}: could not find the Filters type import to extend")
        views_import = found[0]
        todo[VIEWS] = views

    if 'n.link.startsWith("/")' in bell:
        print(f"{BELL}: already guarded")
    else:
        require_once(BELL, bell, BELL_ANCHOR)
        todo[BELL] = bell

    if not todo:
        print("already hardened - nothing to do")
        return

    if FILTERS in todo:
        text = todo[FILTERS]
        text = text.replace(FILTERS_HELPER_ANCHOR, FILTERS_HELPER_ADD + FILTERS_HELPER_ANCHOR, 1)
        text = text.replace(FILTERS_USE_ANCHOR, FILTERS_USE_NEW, 1)
        FILTERS.write_text(text)
        print(f"patched {FILTERS}: URL dates validated")

    if VIEWS in todo and views_import is not None:
        text = todo[VIEWS]
        text = text.replace(views_import, VIEWS_IMPORT_NEW, 1)
        text = text.replace(VIEWS_ANCHOR, VIEWS_NEW, 1)
        VIEWS.write_text(text)
        print(f"patched {VIEWS}: saved views merge over defaults")

    if BELL in todo:
        BELL.write_text(todo[BELL].replace(BELL_ANCHOR, BELL_NEW, 1))
        print(f"patched {BELL}: notification links allow-listed")


if __name__ == "__main__":
    main()

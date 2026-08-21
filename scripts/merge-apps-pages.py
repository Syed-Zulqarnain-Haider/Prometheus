#!/usr/bin/env python3
"""Merge Spotlight, App Master and App Changes into one page with tabs.

Three sidebar entries for three views of the SAME subject - the app master record. What is
missing from it (Spotlight), what it currently says (App Master), and what someone has
proposed changing (App Changes). Anyone fixing an app bounced between three doors to one
room, and the sidebar spent three of its slots saying "apps".

Now: one entry, three tabs, in workflow order - find what needs fixing, read the record,
clear the approvals queue. The tab lives in the URL (?tab=), so a link to one view is still
a link, and the admin-only tab is hidden from non-admins (cosmetic, as always - each client
still enforces its own access server-side, and an unknown or forbidden ?tab= falls back to
the first tab the caller can actually use rather than rendering nothing).

NOTHING IS REWRITTEN OR DELETED. The merged page composes the three EXISTING clients, and
/spotlight, /app-master and /app-changes keep working exactly as they do today - so every
bookmark, and every "Fill these in ->" link the Spotlight tiles already emit, still resolves.

The script does not guess the component names: it READS each page.tsx and identifies the
one imported client it actually renders, aborting (and printing the pages) if any of them
cannot be identified. The nav rewrite is equally conservative - it removes exactly the three
href lines and inserts one carrying the first entry\'s icon, and if the file does not have
exactly three, it changes nothing and says merging by hand is safer.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

FOOTER = 'Rebuild the frontend, then run its test suite.'

PAYLOAD = """
eyJub3RlIjogInRoaXMgc2NyaXB0IGlzIHNlbGYtZGlzY292ZXJpbmc7IG5vIGFuY2hvcnMifQ==
"""


PAGES = [
    ("spotlight", "/spotlight", "Needs attention", False),
    ("app-master", "/app-master", "All records", True),
    ("app-changes", "/app-changes", "Change requests", False),
]
MERGED = Path("frontend/app/(app)/apps-admin/page.tsx")
CLIENT = Path("frontend/components/apps-admin/apps-admin-client.tsx")
NAV = Path("frontend/lib/nav.ts")

_IMPORT_RE = re.compile(r'^import\s*\{\s*([A-Za-z0-9_]+)\s*\}\s*from\s*"([^"]+)";$', re.M)
_SKIP = {"PageHeader", "Suspense", "Metadata"}


def discover():
    """Find each page's client component by READING the page, never by guessing its name.

    Returns (found, problems). `found` maps slug -> (component, import path). A page whose
    client cannot be identified is a problem, not an assumption - the merged page imports
    these by name, and a wrong guess is a build failure at best.
    """
    found, problems = {}, []
    for slug, _href, _label, _admin in PAGES:
        page = Path(f"frontend/app/(app)/{slug}/page.tsx")
        if not page.exists():
            problems.append(f"  {page.as_posix()}: not found")
            continue
        text = page.read_text()
        hits = [
            (name, path)
            for name, path in _IMPORT_RE.findall(text)
            if name not in _SKIP and f"<{name}" in text
        ]
        if len(hits) != 1:
            problems.append(
                f"  {page.as_posix()}: expected exactly 1 rendered client import, found "
                f"{len(hits)} ({[h[0] for h in hits]})"
            )
            continue
        found[slug] = hits[0]
    return found, problems


def build_client(found):
    """The merged client: three tabs over the EXISTING clients, nothing rewritten."""
    imports = "\n".join(
        f'import {{ {found[slug][0]} }} from "{found[slug][1]}";' for slug, *_ in PAGES
    )
    tabs = ",\n".join(
        f'  {{ id: "{slug}", label: "{label}", adminOnly: {str(admin).lower()} }}'
        for slug, _href, label, admin in PAGES
    )
    panels = "\n".join(
        f'      {{active === "{slug}" && <{found[slug][0]} />}}' for slug, *_ in PAGES
    )
    return f'''"use client";

import {{ useRouter, useSearchParams }} from "next/navigation";

{imports}
import {{ useMe }} from "@/lib/api-hooks";
import {{ cn }} from "@/lib/utils";

/** One page for one subject: the app master record.
 *
 *  These were three sidebar entries - Spotlight, App Master, App Changes - for three views
 *  of the SAME thing: what is missing from a record, what the record says, and what someone
 *  has proposed changing. Three doors to one room meant a person fixing an app bounced
 *  between them, and the sidebar spent three slots saying "apps".
 *
 *  Tab order follows the actual workflow: find what needs fixing, look at the record, then
 *  the approvals queue. The tab lives in the URL (?tab=), so a link to a specific view is
 *  still a link - and the existing /spotlight, /app-master and /app-changes routes keep
 *  working untouched, so no bookmark or deep link breaks.
 *
 *  Hiding the admin-only tab is COSMETIC, as always here: each client enforces its own
 *  access server-side, and this only spares non-admins a tab that would refuse them.
 */
const TABS = [
{tabs},
];

export function AppsAdminClient() {{
  const router = useRouter();
  const params = useSearchParams();
  const {{ data: me }} = useMe();
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;

  const visible = TABS.filter((tab) => isAdmin || !tab.adminOnly);
  const requested = params.get("tab");
  // Fall back rather than render nothing: an unknown or now-forbidden ?tab= (a shared link
  // to the admin view, opened by a pod owner) lands on the first tab they can actually use.
  const active = visible.some((tab) => tab.id === requested) ? requested : visible[0]?.id;

  function select(id: string) {{
    const next = new URLSearchParams(params.toString());
    next.set("tab", id);
    router.replace(`?${{next.toString()}}`, {{ scroll: false }});
  }}

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b" role="tablist">
        {{visible.map((tab) => (
          <button
            key={{tab.id}}
            type="button"
            role="tab"
            aria-selected={{active === tab.id}}
            onClick={{() => select(tab.id)}}
            className={{cn(
              "-mb-px border-b-2 px-3 py-2 text-sm transition-colors",
              active === tab.id
                ? "border-[color:var(--color-accent)] font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}}
          >
            {{tab.label}}
          </button>
        ))}}
      </div>

{panels}
    </div>
  );
}}
'''


MERGED_PAGE = '''import type { Metadata } from "next";
import { Suspense } from "react";

import { AppsAdminClient } from "@/components/apps-admin/apps-admin-client";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Apps - Prometheus" };

export default function AppsAdminPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Apps"
        description="What needs fixing, what the record says, and what has been proposed - one subject, one page."
      />
      <Suspense>
        <AppsAdminClient />
      </Suspense>
    </div>
  );
}
'''


def rewrite_nav():
    """Collapse the three sidebar entries into one, keeping their icon if we can.

    Line-based and conservative: it removes exactly the lines that declare the three
    hrefs and inserts one in their place. If the file does not look the way we expect
    (any count other than the three), it changes NOTHING and says so.
    """
    if not NAV.exists():
        return "nav.ts not found"
    text = NAV.read_text()
    if 'href: "/apps-admin"' in text:
        return "ALREADY"  # merged on a previous run - say so rather than claim a write
    lines = text.splitlines(keepends=True)
    targets = [i for i, line in enumerate(lines)
               if any(f'href: "{href}"' in line for _s, href, _l, _a in PAGES)]
    if len(targets) != len(PAGES):
        return (f"expected {len(PAGES)} nav entries for the merged pages, found "
                f"{len(targets)} - nav.ts has changed shape, merging it by hand is safer")
    # Reuse the icon from the FIRST of the three so the sidebar keeps a familiar glyph.
    icon = re.search(r"icon:\s*([A-Za-z0-9_]+)", lines[targets[0]])
    if not icon:
        return "could not read an icon from the first nav entry"
    merged = f'  {{ href: "/apps-admin", label: "Apps", icon: {icon.group(1)} }},\n'
    keep = [line for i, line in enumerate(lines) if i not in set(targets)]
    keep.insert(targets[0], merged)
    NAV.write_text("".join(keep))
    return None

def main() -> int:
    if not Path("frontend/app").is_dir():
        print("ABORTED: run this from the repository root")
        return 1

    found, problems = discover()
    if problems:
        print("ABORTED - NOTHING was written. The three pages could not be read:")
        print()
        for problem in problems:
            print(problem)
        for slug, *_ in PAGES:
            page = Path(f"frontend/app/(app)/{slug}/page.tsx")
            if page.exists():
                print()
                print(f"----- {page.as_posix()} -----")
                print(page.read_text())
        return 1

    for slug, *_ in PAGES:
        print(f"found {slug:12s} -> {found[slug][0]} from {found[slug][1]}")

    client = build_client(found)

    # Never emit TSX again without checking it first. These files are BUILT from string
    # templates, and a template that is an f-string needs doubled braces while a plain one
    # must not have them - a distinction invisible on review that shipped `import type {{
    # Metadata }}` and broke the frontend build. Refusing to write is free; a red build on
    # the server is a whole round trip.
    for name, content in (("client", client), ("page", MERGED_PAGE)):
        if "{{" in content or "}}" in content:
            print(f"ABORTED: generated {name} still contains doubled braces - the template")
            print("is an f-string/plain-string mix-up. Nothing was written.")
            return 1

    wrote = []
    for path, content in ((CLIENT, client), (MERGED, MERGED_PAGE)):
        if path.exists() and path.read_text() == content:
            print(f"skip  {path.as_posix()}: already present")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        wrote.append(path.as_posix())
    for path in wrote:
        print(f"wrote {path}")

    outcome = rewrite_nav()
    if outcome == "ALREADY":
        print("skip  frontend/lib/nav.ts: already merged")
    elif outcome:
        print(f"nav.ts NOT changed: {outcome}")
        print("The merged page exists and works; only the sidebar still lists three entries.")
        return 1
    else:
        print("wrote frontend/lib/nav.ts  (three entries -> one)")

    print()
    print(FOOTER)
    return 0


if __name__ == "__main__":
    sys.exit(main())

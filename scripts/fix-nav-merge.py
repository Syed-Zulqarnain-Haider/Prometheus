#!/usr/bin/env python3
"""Repair nav.ts and merge the three app entries - by PARSING entries, not deleting lines.

WHAT WENT WRONG. merge-apps-pages.py collapsed the sidebar by removing the lines that
contained each href. That works only if every entry is written on one line. The deployed
nav.ts has a MULTI-LINE entry:

    {
      href: "/app-changes",
      label: "App Changes",
      icon: ClipboardCheck,
      requiresRole: ["pod_owner"],
    },

so deleting "the href line" left a headless object, and the build failed with
"Property 'href' is missing in type". A line is not an entry; assuming it was is the bug.

This walks the NAV_ITEMS array and matches braces, so an entry is an ENTRY however it is
formatted. It also REPAIRS the damage: any entry left without an href is removed. Then it
drops the three merged hrefs, inserts one, and deletes icon imports nothing references any
more (the previous run left an unused `Database`, which is a lint error in this repo).

Idempotent, and it changes nothing unless it can account for every entry it touches.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAV = Path("frontend/lib/nav.ts")
MERGE_HREFS = ("/spotlight", "/app-master", "/app-changes")
MERGED_HREF = "/apps-admin"
MERGED_LABEL = "Apps"


def split_entries(body: str) -> list[str]:
    """Split the array body into entries by matching braces - format-agnostic."""
    entries, depth, start, in_string, quote = [], 0, None, False, ""
    for index, char in enumerate(body):
        if in_string:
            if char == quote and body[index - 1] != "\\":
                in_string = False
            continue
        if char in "\"'`":
            in_string, quote = True, char
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                end = body.find(",", index)
                end = end + 1 if end != -1 else index + 1
                entries.append(body[start:end])
                start = None
    return entries


def main() -> int:
    if not NAV.exists():
        print("ABORTED: frontend/lib/nav.ts not found - run from the repository root")
        return 1
    source = NAV.read_text()

    match = re.search(r"(export const NAV_ITEMS[^=]*=\s*\[)(.*?)(\n\];)", source, re.S)
    if not match:
        print("ABORTED: could not find the NAV_ITEMS array - nav.ts has changed shape.")
        print("-" * 60)
        print(source)
        return 1
    head, body, tail = match.groups()

    entries = split_entries(body)
    if not entries:
        print("ABORTED: no nav entries parsed - nothing was changed.")
        return 1

    # ONE FULL PASS FIRST, then decide. The previous version returned the moment it saw
    # an /apps-admin entry - so on a half-finished tree, where the merged entry already
    # exists AND a headless corpse is still sitting further down, it declared success and
    # left the file broken. An early return inside a scan is a decision made on partial
    # information; that is exactly what went wrong.
    kept, removed, repaired = [], [], []
    insert_at = None      # where the FIRST merged entry sat, so the group keeps its place
    already_merged = False
    for entry in entries:
        href = re.search(r'href:\s*"([^"]+)"', entry)
        if href is None:
            # The corpse a line-based delete leaves behind. Removing it is the repair.
            repaired.append(" ".join(entry.split())[:70])
            if insert_at is None:
                insert_at = len(kept)
            continue
        if href.group(1) == MERGED_HREF:
            already_merged = True
            if insert_at is None:
                insert_at = len(kept)
            continue          # dropped here, re-inserted below - never duplicated
        if href.group(1) in MERGE_HREFS:
            if insert_at is None:
                insert_at = len(kept)
            removed.append(href.group(1))
            continue
        kept.append(entry)

    if already_merged and not removed and not repaired:
        print("skip  nav.ts: already merged, nothing to repair")
        return 0

    if not removed and not repaired and not already_merged:
        print("ABORTED: none of the three entries were found, and nothing needed repair.")
        print("Merging by hand is safer than guessing. Current entries:")
        for entry in entries:
            print("  " + " ".join(entry.split())[:80])
        return 1

    # Keep a familiar glyph: reuse an icon one of the merged entries already used.
    # Prefer an icon one of the three already used. On a REPAIR run they are mostly gone
    # already, so fall back to the headless entry's icon - which is exactly the glyph the
    # sidebar was showing before it broke.
    icon = None
    for entry in entries:
        href = re.search(r'href:\s*"([^"]+)"', entry)
        if href and href.group(1) in MERGE_HREFS:
            found = re.search(r"icon:\s*([A-Za-z0-9_]+)", entry)
            if found:
                icon = found.group(1)
                break
    if icon is None:
        for entry in entries:
            if re.search(r'href:\s*"', entry):
                continue
            found = re.search(r"icon:\s*([A-Za-z0-9_]+)", entry)
            if found:
                icon = found.group(1)
                break
    if icon is None:
        for entry in entries:
            href = re.search(r'href:\s*"([^"]+)"', entry)
            if href and href.group(1) == MERGED_HREF:
                found = re.search(r"icon:\s*([A-Za-z0-9_]+)", entry)
                if found:
                    icon = found.group(1)
                    break
    if icon is None:
        print("ABORTED: could not read an icon from the merged or damaged entries.")
        return 1

    merged = f'  {{ href: "{MERGED_HREF}", label: "{MERGED_LABEL}", icon: {icon} }},'
    # Insert where the FIRST of the three sat, so the sidebar keeps its familiar order
    # instead of the merged entry jumping to the top.
    if insert_at is None:
        insert_at = len(kept)
    rendered = ["\n  " + entry.strip() for entry in kept]
    rendered.insert(insert_at, "\n" + merged)
    new_body = "".join(rendered)

    updated = source[: match.start()] + head + new_body + tail + source[match.end() :]

    # Drop icon imports nothing references any more - an unused import is a lint error here.
    import_match = re.search(r"import \{\n(.*?)\n\} from \"lucide-react\";", updated, re.S)
    dropped = []
    if import_match:
        names = [n.strip().rstrip(",") for n in import_match.group(1).splitlines() if n.strip()]
        after_imports = updated[import_match.end() :]
        alive = [n for n in names if re.search(rf"\b{re.escape(n)}\b", after_imports)]
        dropped = [n for n in names if n not in alive]
        if dropped:
            block = "import {\n" + "".join(f"  {n},\n" for n in alive) + '} from "lucide-react";'
            updated = updated[: import_match.start()] + block + updated[import_match.end() :]

    # Never hand back a nav.ts that cannot type-check. Every entry must carry an href -
    # the exact property whose absence broke the build twice. Checking the OUTPUT costs
    # nothing; shipping it and finding out on the server costs a round trip each time.
    check = re.search(r"export const NAV_ITEMS[^=]*=\s*\[(.*?)\n\];", updated, re.S)
    if not check:
        print("ABORTED: the rewritten array could not be re-parsed - nothing was written.")
        return 1
    for entry in split_entries(check.group(1)):
        if not re.search(r'href:\s*"', entry):
            print("ABORTED: the rewrite would leave an entry with no href:")
            print("  " + " ".join(entry.split())[:80])
            print("Nothing was written.")
            return 1

    NAV.write_text(updated)
    if repaired:
        for entry in repaired:
            print(f"repaired  removed an entry with no href: {entry}")
    print(f"merged    {', '.join(removed) or '(already gone)'} -> {MERGED_HREF}")
    if dropped:
        print(f"cleaned   unused icon import(s): {', '.join(dropped)}")
    print("wrote frontend/lib/nav.ts")
    print()
    print("Rebuild the frontend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

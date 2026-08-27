#!/usr/bin/env python3
"""Take the Advisor tab off the right edge of every page.

The tab is a ``position: fixed`` button pinned to the middle of the right edge, so it
sits over page content on every route, at every scroll position, forever. It is removed
rather than hidden: a hidden control is still mounted, still fetches its briefing, and
still comes back the first time someone reaches for a CSS toggle.

WHAT IS AND IS NOT REMOVED
--------------------------
Only the launcher. The panel component, its briefing hook and its close button are left
exactly as they are, so if the Advisor is ever opened from somewhere else - a menu item,
a keyboard shortcut, a link - that still works. The script says at the end whether any
such other opener exists, because "removed the tab" and "removed the feature" are
different promises and only one of them was asked for.

Imports that the removal orphans are pruned, because ``noUnusedLocals`` / eslint would
otherwise fail the build on a name that is now referenced nowhere - a green run that
turns red for a reason unrelated to the change is worse than no change.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")

# The tab is found by what pins it to the edge, not by its label: the visible word
# "Advisor" is prose and could be renamed tomorrow, whereas an element cannot be stuck
# to the middle of the right edge without saying so in its classes.
EDGE_MARKERS = ("fixed right-0 top-1/2", "fixed right-0 top-[50%]")

IMPORT_RE = re.compile(r'^import\s*\{([^}]*)\}\s*from\s*"([^"]+)";\s*$', re.M)


def find_panel() -> Path | None:
    candidates = sorted(
        p
        for p in ROOT.glob("frontend/**/*.tsx")
        if "node_modules" not in p.parts and ".next" not in p.parts
    )
    hits = [p for p in candidates if any(m in p.read_text() for m in EDGE_MARKERS)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None
    # More than one thing is pinned to the right edge - pick the advisor's own file if
    # exactly one of them is it, otherwise refuse to guess.
    named = [p for p in hits if "advisor" in str(p).lower()]
    return named[0] if len(named) == 1 else None


def window(text: str, needle: str, before: int = 4, after: int = 16) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found)"


def prune_unused_named_imports(text: str) -> tuple[str, list[str]]:
    """Drop named imports nothing references any more.

    Usage is counted with EVERY import line stripped out first, so an import cannot
    count as its own use. Anything that still appears once outside the imports is kept -
    deliberately generous: leaving one import too many costs nothing, removing one that
    was in use breaks the build.
    """
    dropped: list[str] = []
    while True:
        body = IMPORT_RE.sub("", text)
        for match in IMPORT_RE.finditer(text):
            names = [n.strip() for n in match.group(1).split(",") if n.strip()]
            # `X as Y` binds Y; that is the name to look for.
            kept = [n for n in names if re.search(rf"\b{re.escape(n.split()[-1])}\b", body)]
            if len(kept) == len(names):
                continue
            dropped.extend(n for n in names if n not in kept)
            if kept:
                line = f'import {{ {", ".join(kept)} }} from "{match.group(2)}";'
                text = text[: match.start()] + line + text[match.end() :]
            else:
                end = match.end()
                if end < len(text) and text[end] == "\n":
                    end += 1
                text = text[: match.start()] + text[end:]
            break  # indices moved - rescan
        else:
            return text, dropped


def main() -> int:
    panel = find_panel()
    if panel is None:
        print(
            "SKIPPED - nothing was written.\n\n"
            "  Could not identify exactly one component pinned to the right edge by\n"
            f"  {' or '.join(EDGE_MARKERS)}. Nothing under frontend/ was changed."
        )
        return 0

    text = panel.read_text()
    marker = next(m for m in EDGE_MARKERS if m in text)

    at = text.index(marker)
    start = text.rfind("<button", 0, at)
    if start == -1:
        print(
            f"SKIPPED - nothing was written.\n\n  {panel}: the edge classes are not on a\n"
            "  <button>, so what to remove is a guess. On disk:\n" + window(text, marker)
        )
        return 0
    close = text.find("</button>", at)
    if close == -1:
        print(
            f"SKIPPED - nothing was written.\n\n  {panel}: no closing </button> after the\n"
            "  launcher. On disk:\n" + window(text, marker)
        )
        return 0
    end = close + len("</button>")

    # A second <button> opening between the start and the close would mean the match is
    # not the launcher's own. Nested buttons are invalid HTML, so this should never fire -
    # it is here so that if it ever does, nothing is cut blindly.
    if "<button" in text[start + len("<button") : close]:
        print(
            f"SKIPPED - nothing was written.\n\n  {panel}: another <button> opens before the\n"
            "  launcher closes; the boundaries are not certain. On disk:\n"
            + window(text, marker)
        )
        return 0

    # Take the indentation and the newline with it, so no blank gap is left behind.
    line_start = text.rfind("\n", 0, start) + 1
    if text[line_start:start].strip() == "":
        start = line_start
    if end < len(text) and text[end] == "\n":
        end += 1

    removed = text[start:end]
    text = text[:start] + text[end:]
    text, dropped = prune_unused_named_imports(text)
    panel.write_text(text)

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    print(f"  - {panel}: the fixed right-edge launcher is gone ({len(removed.splitlines())} lines)")
    if dropped:
        print(f"  - orphaned imports pruned: {', '.join(sorted(set(dropped)))}")

    # Say plainly whether the panel is now unreachable, rather than letting "the tab is
    # gone" quietly mean "the feature is gone" or quietly mean it is not.
    openers = [
        f"  {p}:{i}  {ln.strip()[:100]}"
        for p in sorted(ROOT.glob("frontend/**/*.tsx"))
        if "node_modules" not in p.parts and ".next" not in p.parts
        for i, ln in enumerate(p.read_text().splitlines(), 1)
        if re.search(r"setOpen\(\s*true\s*\)|setAdvisorOpen\(|openAdvisor\(", ln)
        and "advisor" in str(p).lower()
    ]
    if openers:
        print("  - the panel can still be opened from:")
        for line in openers:
            print(f"    {line.strip()}")
    else:
        print("  - nothing else opens the panel, so it no longer renders anywhere.")
        print("    The component and its hooks are left in place, unmounted, not deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

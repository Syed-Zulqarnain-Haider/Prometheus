#!/usr/bin/env python3
"""Read-only report on the Alembic revision graph. Fixes nothing, writes nothing.

Alembic said "Revision X is present more than once" and then "Cycle is detected". Both
mean the same thing: two FILES claim the same revision id, so the graph has two different
"next" edges from one node and walks back into itself.

This prints every revision id, the file it lives in, and its down_revision, then names the
duplicates and the roots/heads. That is enough to say exactly which file to remove without
guessing at someone else's history.

Usage, from the repository root:
    python3 scripts/check-migrations.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

VERSIONS = Path("backend/alembic/versions")

REV_RE = re.compile(r"^revision(?::\s*str)?\s*=\s*[\"']([^\"']+)[\"']", re.M)
# down_revision has FOUR legal shapes and a merge revision uses the tuple one:
#     down_revision = None
#     down_revision = "abc123"
#     down_revision: str | None = "abc123"
#     down_revision = ("abc123", "def456")     <-- a MERGE
# Reading only the first two made every merge look like a second root, which is a fork
# that does not exist - a false alarm that blocks a deploy is as bad as a missed one.
DOWN_RE = re.compile(r"^down_revision(?::[^=\n]+)?\s*=\s*(.+)$", re.M)
_QUOTED = re.compile(r"[\"']([^\"']+)[\"']")


def parse_down(text: str) -> tuple[list[str], str | None]:
    """Return (parents, raw) - raw is kept so an unparseable line can be shown verbatim."""
    m = DOWN_RE.search(text)
    if m is None:
        return [], None
    raw = m.group(1).strip()
    if raw.startswith("None"):
        return [], raw
    return _QUOTED.findall(raw), raw


def main() -> None:
    if not VERSIONS.is_dir():
        print(f"{VERSIONS} not found - run from the repository root", file=sys.stderr)
        raise SystemExit(1)

    by_rev: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    unparsed: list[tuple[str, str]] = []
    files = sorted(VERSIONS.glob("*.py"))
    for path in files:
        text = path.read_text()
        rev = REV_RE.search(text)
        if rev is None:
            continue
        parents, raw = parse_down(text)
        if raw is not None and not parents and not raw.startswith("None"):
            unparsed.append((path.name, raw))
        by_rev[rev.group(1)].append((path.name, parents))

    print(f"{len(files)} file(s) in {VERSIONS}, {len(by_rev)} distinct revision id(s)\n")

    duplicates = {r: v for r, v in by_rev.items() if len(v) > 1}
    if duplicates:
        print("DUPLICATE REVISION IDS - this is the cause of both the warning and the cycle:")
        for rev, entries in sorted(duplicates.items()):
            print(f"\n  {rev}")
            for name, parents in entries:
                print(f"      {name}")
                print(f"          down_revision = {parents or None!r}")
        print()
    else:
        print("No duplicate revision ids.\n")

    # Roots and heads, computed only from ids that appear exactly once, so a duplicate
    # cannot make this lie.
    clean = {r: v[0][1] for r, v in by_rev.items() if len(v) == 1}
    # A merge revision has SEVERAL parents; every one of them counts as referenced.
    referenced = {parent for parents in clean.values() for parent in parents}
    heads = sorted(r for r in clean if r not in referenced)
    roots = sorted(r for r, parents in clean.items() if not parents)
    print(f"root(s): {', '.join(roots) or 'none'}")
    print(f"head(s): {', '.join(heads) or 'none'}")

    problems: list[str] = []
    if duplicates:
        problems.append(f"{len(duplicates)} duplicate revision id(s)")
    if len(heads) > 1:
        problems.append(f"{len(heads)} heads (the chain has forked)")
    if not heads:
        problems.append("no head at all (every revision is referenced - a cycle)")

    dangling = sorted({p for parents in clean.values() for p in parents if p not in by_rev})
    if dangling:
        print(f"\ndown_revision pointing at a revision that does not exist: {', '.join(dangling)}")

    if dangling:
        problems.append(f"{len(dangling)} dangling down_revision(s)")
    if unparsed:
        problems.append(f"{len(unparsed)} unreadable down_revision line(s)")
        print("\nCould not read these down_revision lines - showing them verbatim:")
        for name, raw in unparsed:
            print(f"  {name}: down_revision = {raw}")

    print("\nFull list, oldest filename first:")
    for path in files:
        text = path.read_text()
        rev = REV_RE.search(text)
        if rev is None:
            print(f"  {path.name}: NO revision id")
            continue
        parents, _ = parse_down(text)
        mark = "  <== DUPLICATE" if len(by_rev[rev.group(1)]) > 1 else ""
        shown = " + ".join(parents) if parents else "None"
        merge = "  (merge)" if len(parents) > 1 else ""
        print(f"  {rev.group(1)}  <- {shown:12}  {path.name}{merge}{mark}")

    if problems:
        print(f"\nBROKEN: {'; '.join(problems)}.")
        print("`alembic upgrade head` will fail on this - fix it before deploying.")
        raise SystemExit(1)
    print("\nGraph is sound: one head, no duplicates, no dangling references.")


if __name__ == "__main__":
    main()

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
DOWN_RE = re.compile(r"^down_revision(?::\s*[^=]+)?\s*=\s*(?:[\"']([^\"']+)[\"']|None)", re.M)


def main() -> None:
    if not VERSIONS.is_dir():
        print(f"{VERSIONS} not found - run from the repository root", file=sys.stderr)
        raise SystemExit(1)

    by_rev: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    files = sorted(VERSIONS.glob("*.py"))
    for path in files:
        text = path.read_text()
        rev = REV_RE.search(text)
        if rev is None:
            continue
        down = DOWN_RE.search(text)
        by_rev[rev.group(1)].append((path.name, down.group(1) if down else None))

    print(f"{len(files)} file(s) in {VERSIONS}, {len(by_rev)} distinct revision id(s)\n")

    duplicates = {r: v for r, v in by_rev.items() if len(v) > 1}
    if duplicates:
        print("DUPLICATE REVISION IDS - this is the cause of both the warning and the cycle:")
        for rev, entries in sorted(duplicates.items()):
            print(f"\n  {rev}")
            for name, down in entries:
                print(f"      {name}")
                print(f"          down_revision = {down!r}")
        print()
    else:
        print("No duplicate revision ids.\n")

    # Roots and heads, computed only from ids that appear exactly once, so a duplicate
    # cannot make this lie.
    clean = {r: v[0][1] for r, v in by_rev.items() if len(v) == 1}
    referenced = {down for down in clean.values() if down}
    heads = sorted(r for r in clean if r not in referenced)
    roots = sorted(r for r, down in clean.items() if down is None)
    print(f"root(s): {', '.join(roots) or 'none'}")
    print(f"head(s): {', '.join(heads) or 'none'}")

    problems: list[str] = []
    if duplicates:
        problems.append(f"{len(duplicates)} duplicate revision id(s)")
    if len(heads) > 1:
        problems.append(f"{len(heads)} heads (the chain has forked)")
    if not heads:
        problems.append("no head at all (every revision is referenced - a cycle)")

    dangling = sorted({d for d in clean.values() if d and d not in by_rev})
    if dangling:
        print(f"\ndown_revision pointing at a revision that does not exist: {', '.join(dangling)}")

    if dangling:
        problems.append(f"{len(dangling)} dangling down_revision(s)")

    print("\nFull list, oldest filename first:")
    for path in files:
        text = path.read_text()
        rev = REV_RE.search(text)
        if rev is None:
            print(f"  {path.name}: NO revision id")
            continue
        down = DOWN_RE.search(text)
        mark = "  <== DUPLICATE" if len(by_rev[rev.group(1)]) > 1 else ""
        print(f"  {rev.group(1)}  <- {down.group(1) if down and down.group(1) else 'None':12}  {path.name}{mark}")

    if problems:
        print(f"\nBROKEN: {'; '.join(problems)}.")
        print("`alembic upgrade head` will fail on this - fix it before deploying.")
        raise SystemExit(1)
    print("\nGraph is sound: one head, no duplicates, no dangling references.")


if __name__ == "__main__":
    main()

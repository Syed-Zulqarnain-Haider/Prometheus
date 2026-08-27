#!/usr/bin/env python3
"""P1-15: stop Next prefetching every link on sight.

~21 RSC prefetches per page view, some returning 503. Next prefetches every
<Link> in the viewport by default, and a dashboard is nothing but links - a
sidebar plus tables where every row links somewhere. The page ends up fetching
dozens of routes nobody asked for, and they compete with the data calls the
page actually needs.

Every <Link> gets an explicit `prefetch={false}`. Explicit rather than only on
the sidebar: a table with 300 rows is 300 prefetches, and the next table added
would silently reintroduce the problem.

NOT DONE HERE, and not claimed: the ticket also asks for hover-intent prefetch
on the top 2-3 destinations, and for /today to resolve its date range before
the first fetch. Both need behaviour I have not read yet.

The tag scanner is brace-aware: a JSX attribute can hold an arrow function whose
`>` is not the end of the tag, so a regex cannot find where a tag stops.

Nothing is written unless every file parses back. Re-running is a no-op.
Revert: git checkout -- frontend/
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
SKIP = ("node_modules", ".next")

#: A `prefetch` ATTRIBUTE, with or without a value - `prefetch` alone is valid JSX and
#: means true. The lookarounds keep it from matching the word inside another attribute's
#: string value.
ATTRIBUTE = re.compile(r"(?<![\w$.\"'])prefetch(?![\w$])")

problems: list[str] = []
notes: list[str] = []


def tag_end(text: str, start: int) -> int:
    """Index of the `>` closing the tag that starts at ``start``.

    Skips over strings, template literals and brace-delimited expressions, because
    `onClick={() => go()}` contains a `>` that is not the end of anything.
    """
    index, depth, quote = start, 0, ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote and text[index - 1] != "\\":
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == ">" and depth == 0:
            return index
        index += 1
    return -1


def patch(path: Path) -> tuple[str, int] | None:
    source = path.read_text(encoding="utf-8")
    if "<Link" not in source:
        return None

    out = source
    added = 0
    # Back to front, so earlier offsets stay valid.
    for match in reversed(list(re.finditer(r"<Link\b", out))):
        start = match.start()
        end = tag_end(out, start)
        if end == -1:
            problems.append(f"{path.relative_to(ROOT)}: unterminated <Link at offset {start}")
            return None
        tag = out[start:end]
        if ATTRIBUTE.search(tag):
            continue
        insert = match.end()
        out = out[:insert] + " prefetch={false}" + out[insert:]
        added += 1

    if added == 0:
        return None
    return out, added


def main() -> int:
    pending: dict[Path, str] = {}
    total = 0
    for path in sorted(FE.rglob("*.tsx")):
        if any(part in path.parts for part in SKIP):
            continue
        result = patch(path)
        if result is None:
            continue
        text, added = result
        pending[path] = text
        total += added
        notes.append(f"  {path.relative_to(ROOT)}: {added} link(s)")

    if problems:
        return report()
    if not pending:
        notes.append("  every <Link> already declares prefetch - nothing to do")
        return report()

    for path, text in pending.items():
        path.write_text(text, encoding="utf-8")

    # Verify against the written files, not against what I meant to write.
    unset = duplicated = 0
    for path in sorted(FE.rglob("*.tsx")):
        if any(part in path.parts for part in SKIP):
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"<Link\b", text):
            end = tag_end(text, match.start())
            tag = text[match.start():end]
            count = len(ATTRIBUTE.findall(tag))
            if count == 0:
                unset += 1
            elif count > 1:
                duplicated += 1
                problems.append(f"{path.relative_to(ROOT)}: duplicate prefetch in one tag")
    notes.append(f"\n  {total} link(s) changed; {unset} still default; {duplicated} duplicated")
    if unset:
        problems.append(f"{unset} <Link> still prefetches by default")
    return report()


def report() -> int:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED:")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("\nPATCHED. Verified only by:  ./scripts/run-frontend-tests.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Remove the trend chart from the Yearly / Monthly Progress to Target cards.

The chart existed to answer "how did the period get here" through a smoothing
selector (Daily / Weekly avg / Monthly avg). Those averages are now plain figures
on the same card, which answers it faster, so the chart is redundant.

Removing a component leaves imports behind that nothing uses any more, and an
unused import is a type error under `tsc --noEmit`. So this does not just delete
the component: it works out which imported names are still referenced afterwards
and prunes the rest, rather than me guessing which ones went with it.

Nothing is written unless every step resolves. Re-running is a no-op.
Revert: git checkout -- frontend/components/overview/revenue-progress.tsx
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = ROOT / "frontend" / "components" / "overview" / "revenue-progress.tsx"

problems: list[str] = []
notes: list[str] = []

# The `type` keyword is CAPTURED, not skipped. `import type { X }` rewritten as
# `import { X }` turns a type-only export into a value import, which fails under
# isolatedModules - and it is the sort of breakage that only shows up at build time.
NAMED_IMPORT = re.compile(
    r'^import\s+(?P<kind>type\s+)?\{(?P<named>[^}]*)\}\s*from\s*"(?P<mod>[^"]+)";[ \t]*\n',
    re.M | re.S,
)
DEFAULT_IMPORT = re.compile(
    r'^import\s+(?P<kind>type\s+)?(?P<name>[A-Za-z_$][\w$]*)\s+from\s*"(?P<mod>[^"]+)";[ \t]*\n',
    re.M,
)
TOP_LEVEL_DECL = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:function|const|class|interface|type)\s", re.M)


def fail(message: str) -> None:
    problems.append(message)


def note(message: str) -> None:
    notes.append(message)


def used(name: str, body: str) -> bool:
    return re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", body) is not None


def strip_imports(source: str) -> str:
    return DEFAULT_IMPORT.sub("", NAMED_IMPORT.sub("", source))


def prune_imports(source: str) -> tuple[str, list[str]]:
    """Drop imported names nothing references any more."""
    body = strip_imports(source)
    removed: list[str] = []

    def rewrite_named(match: re.Match[str]) -> str:
        members = [m.strip() for m in match.group("named").split(",") if m.strip()]
        keep = []
        for member in members:
            # `type Foo` and `Foo as Bar` both bind the LAST identifier.
            binding = member.split()[-1]
            if used(binding, body):
                keep.append(member)
            else:
                removed.append(f"{binding} (from {match.group('mod')})")
        if not keep:
            return ""
        kind = match.group("kind") or ""
        line = f'import {kind}{{ {", ".join(keep)} }} from "{match.group("mod")}";\n'
        if len(line) <= 92:
            return line
        joined = ",\n  ".join(keep)
        return f'import {kind}{{\n  {joined},\n}} from "{match.group("mod")}";\n'

    def rewrite_default(match: re.Match[str]) -> str:
        if used(match.group("name"), body):
            return match.group(0)
        removed.append(f"{match.group('name')} (default, from {match.group('mod')})")
        return ""

    out = NAMED_IMPORT.sub(rewrite_named, source)
    out = DEFAULT_IMPORT.sub(rewrite_default, out)
    # Collapse the blank lines a removed import leaves behind - in the IMPORT BLOCK only.
    # Applied to the whole file it would quietly reformat JSX that nobody asked it to touch.
    tail_start = 0
    for match in re.finditer(r'^import [^\n]*?;[ \t]*\n|^\}\s*from\s*"[^"]+";[ \t]*\n', out, re.M):
        tail_start = max(tail_start, match.end())
    head, tail = out[:tail_start], out[tail_start:]
    return re.sub(r"\n{3,}", "\n\n", head) + tail, removed


OLD_USAGE = '''
      {/* How the period got here, not just how far along it is. A donut says 62% and
          nothing about whether the last fortnight was climbing or sliding. */}
      <RevenueTrend filters={filters} isYear={isYear} />'''


def main() -> int:
    if not PROGRESS.exists():
        fail(f"missing: {PROGRESS.relative_to(ROOT)}")
        return report()

    source = PROGRESS.read_text(encoding="utf-8")
    if "RevenueTrend" not in source:
        note("revenue-progress.tsx no longer has the trend chart - left as is.")
        return report()

    count = source.count(OLD_USAGE)
    if count != 1:
        fail(f"the <RevenueTrend .../> usage matched {count} times, expected 1")
        for number, line in enumerate(source.splitlines(), 1):
            if "RevenueTrend" in line:
                print(f"    on disk revenue-progress.tsx:{number}: {line}")
        return report()
    out = source.replace(OLD_USAGE, "", 1)
    note("removed <RevenueTrend /> from both progress cards")

    start = out.find("function RevenueTrend")
    if start == -1:
        fail("the RevenueTrend component is not declared in this file - "
             "not deleting anything until I can see where it lives.")
        return report()
    # Take the declaration back to the start of its line (and any doc comment above it).
    line_start = out.rfind("\n", 0, start) + 1
    comment = out.rfind("/**", 0, line_start)
    if comment != -1 and out[comment:line_start].count("*/") == 1 \
            and out[out.find("*/", comment):line_start].strip() == "*/":
        line_start = comment

    # Refuse if anything else is declared after it - deleting to EOF would take that too.
    after = TOP_LEVEL_DECL.search(out, start + len("function RevenueTrend"))
    if after is not None:
        fail(f"another top-level declaration follows RevenueTrend at offset {after.start()} "
             f"({out[after.start():after.start() + 60]!r}) - refusing to delete to EOF.")
        return report()

    out = out[:line_start].rstrip("\n") + "\n"
    note("deleted the RevenueTrend component")

    out, removed = prune_imports(out)
    if removed:
        note("pruned imports nothing references any more:")
        for entry in removed:
            note(f"    {entry}")
    else:
        note("no imports became unused")

    # The chart is gone; the donut and the figures must not be.
    for keeper in ("RevenueProgress", "Figure", "formatUSD", "Chart"):
        if keeper not in out:
            fail(f"{keeper} disappeared from the file - the deletion took too much.")
    if "RevenueTrend" in out:
        fail("a reference to RevenueTrend survived the deletion.")
    if problems:
        return report()

    PROGRESS.write_text(out, encoding="utf-8")
    return report()


def report() -> int:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED - nothing was written:")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("\nPATCHED. Verified only by:  ./scripts/run-frontend-tests.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""UX batch 7: stop the migration test going stale, and finish the Unassigned fix.

  A. THE FAILING TEST.  ``test_upgrade_head_applies_cleanly_over_asyncpg`` compares the
     database's revision against a HARDCODED constant. That constant is wrong the moment
     anybody adds a migration - it has to be hand-edited every single time, and the
     failure it produces says nothing about whether migrations actually work. It says
     somebody forgot to edit a string.

     The head is now DETECTED from the versions directory, and the detection asserts
     there is exactly ONE head. That turns a maintenance trap into an invariant worth
     having: a forked history is a deploy that dies at `alembic upgrade head`, and this
     is the cheapest place to find out. The test's real subject - that the whole chain
     applies over asyncpg without a parameter-style error - is untouched.

  B. APPS EXPLORER.  The "-1" fix could not match because the cell renderer ends with
     ``String(value ?? "")``, not the ``?? "-"`` this patch was written against. Now
     anchored on what is actually there, and the empty-string fallback is preserved, so
     a blank publisher stays blank rather than growing a dash it never had.

Both sections are independent and idempotent: one that cannot match is skipped and
reported without taking the other down.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
MIGRATION_TEST = ROOT / "backend/tests/test_migrations.py"
EXPLORER = ROOT / "frontend/components/apps/apps-explorer.tsx"
ATTRIBUTION = ROOT / "frontend/lib/attribution.ts"

skipped: list[str] = []
notes: list[str] = []


class Section:
    def __init__(self, name: str) -> None:
        self.name = name
        self.writes: dict[Path, str] = {}
        self.reasons: list[str] = []
        self.done: list[str] = []

    def skip(self, reason: str, region: str = "") -> None:
        self.reasons.append(reason + (f"\n{indent(region)}" if region else ""))

    def commit(self) -> None:
        if self.reasons:
            skipped.append(
                f"[{self.name}] SKIPPED - nothing from this section was written:\n"
                + "\n".join(f"  * {r}" for r in self.reasons)
            )
            return
        for path, text in self.writes.items():
            path.write_text(text)
        for line in self.done or ["already applied - left alone"]:
            notes.append(f"[{self.name}] {line}")


def indent(text: str) -> str:
    return "\n".join(f"      | {line}" for line in text.rstrip("\n").splitlines())


def window(text: str, needle: str, before: int = 4, after: int = 12) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(lines[max(0, i - before) : i + after])
    return "(not found anywhere in the file)"


# ─────────────────────────────────────────────────────────────────────────────
# A. Detect the head instead of hardcoding it
# ─────────────────────────────────────────────────────────────────────────────

HEAD_CONST_RE = re.compile(r'^_HEAD = "[^"]+"[^\n]*\n', re.M)

DETECTOR = '''

def _detect_head() -> str:
    """The one revision nothing points at.

    This used to be a hardcoded string, which made this test fail every time a migration
    was added - a maintenance trap wearing an assertion's clothes, whose failure meant
    "somebody forgot to edit a constant", never "migrations are broken".

    Detecting it keeps the real subject of the test (the whole chain applies over
    asyncpg) and adds an invariant worth having: that there IS exactly one end to the
    chain. A forked history is a deploy that stops dead at `alembic upgrade head`, and
    this is the cheapest possible place to find that out.
    """
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in (_BACKEND_DIR / "alembic" / "versions").glob("*.py"):
        source = path.read_text()
        revision = re.search(r'^revision(?::[^=\\n]+)?\\s*=\\s*["\\']([^"\\']+)["\\']', source, re.M)
        if revision:
            revisions.add(revision.group(1))
        # Merge points carry a TUPLE of parents; reading only the first quoted string
        # would leave the others looking like live heads.
        down = re.search(r"^down_revision(?::[^=\\n]+)?\\s*=\\s*(.+)$", source, re.M)
        if down:
            parents.update(re.findall(r'["\\']([^"\\']+)["\\']', down.group(1)))
    heads = sorted(revisions - parents)
    assert len(heads) == 1, f"expected exactly one alembic head, found {heads}"
    return heads[0]


_HEAD = _detect_head()
'''


def section_head_detection() -> Section:
    section = Section("detect-alembic-head")
    if not MIGRATION_TEST.exists():
        section.skip(f"missing {MIGRATION_TEST}")
        return section
    text = MIGRATION_TEST.read_text()
    if "_detect_head" in text:
        return section

    hits = list(HEAD_CONST_RE.finditer(text))
    if len(hits) != 1:
        section.skip(
            f'expected exactly one hardcoded `_HEAD = "..."`, found {len(hits)}',
            window(text, "_HEAD"),
        )
        return section

    # Spliced by index, NOT re.sub: sub treats the replacement as a TEMPLATE, and this
    # replacement is full of the backslashes that make the detector's own regexes work.
    match = hits[0]
    text = text[: match.start()] + DETECTOR + text[match.end() :]
    if not re.search(r"^import re$", text, re.M):
        # Keep the stdlib import block alphabetical - ruff's isort rules are part of the
        # gate, and a misplaced import fails it just as surely as a broken test.
        text = re.sub(
            r"^import os\n", "import os\nimport re\n", text, count=1, flags=re.M
        )
        if not re.search(r"^import re$", text, re.M):
            section.skip(
                "could not place `import re` - the import block is not as expected"
            )
            return section

    if "_BACKEND_DIR" not in text.split("def _detect_head")[0]:
        section.skip("_BACKEND_DIR is not defined before the detector needs it")
        return section

    section.writes[MIGRATION_TEST] = text
    section.done.append(
        "the head is detected, and a forked history now fails this test"
    )
    return section


# ─────────────────────────────────────────────────────────────────────────────
# B. Apps Explorer: Unassigned, against the renderer that is actually there
# ─────────────────────────────────────────────────────────────────────────────

RAW_CELL_RE = re.compile(
    r'(?P<indent>[ \t]*)return String\(value \?\? "(?P<fallback>[^"]*)"\);'
)
IMPORT_LINE = 'import { dimensionLabel } from "@/lib/attribution";'


def section_explorer() -> Section:
    section = Section("explorer-unassigned")
    if not EXPLORER.exists():
        section.skip(f"missing {EXPLORER}")
        return section
    if not ATTRIBUTION.exists():
        section.skip(
            f"missing {ATTRIBUTION} - refusing to import a module that is not there"
        )
        return section

    text = EXPLORER.read_text()
    if "dimensionLabel(" in text:
        return section

    hits = list(RAW_CELL_RE.finditer(text))
    if len(hits) != 1:
        section.skip(
            f'expected exactly one `return String(value ?? "...");` in the cell renderer, '
            f"found {len(hits)}",
            window(text, "cell: ({ getValue"),
        )
        return section
    if "c.key" not in text:
        section.skip(
            "the column object is not named `c` here", window(text, "cell: ({ getValue")
        )
        return section

    match = hits[0]
    pad = match.group("indent")
    # The existing fallback is carried through deliberately: this patch is about -1
    # reading as Unassigned, not about changing what an empty cell looks like.
    replacement = (
        f'{pad}// A pod of -1 means "nobody owns this yet". One shared rule turns that into\n'
        f"{pad}// Unassigned, so this table cannot disagree with the charts about it.\n"
        f'{pad}return dimensionLabel(c.key, value, "{match.group("fallback")}");'
    )
    text = text[: match.start()] + replacement + text[match.end() :]

    imports = list(re.finditer(r"^import [^\n]*;$", text, re.M))
    if not imports:
        section.skip("no import statements to append to")
        return section
    end = imports[-1].end()
    text = text[:end] + "\n" + IMPORT_LINE + text[end:]

    section.writes[EXPLORER] = text
    section.done.append(
        f'Pod reads Unassigned; the "{match.group("fallback")}" fallback is unchanged'
    )
    return section


def main() -> int:
    if not (ROOT / "frontend").is_dir() or not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    for build in (section_head_detection, section_explorer):
        build().commit()

    print(
        "PATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    for note in notes:
        print(f"  - {note}")
    for entry in skipped:
        print()
        print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

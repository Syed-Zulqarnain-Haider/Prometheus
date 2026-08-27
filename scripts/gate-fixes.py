#!/usr/bin/env python3
"""Two things the gate caught, both consequences of changes already made.

  A. THE TABLE INVENTORY.  ``test_all_schema_tables_registered`` pins the exact set of
     tables the ORM knows about, so a new one is a deliberate act rather than something
     that appears by accident. ``ui_labels`` is deliberate, so it is added to the list.
     That test is doing its job; the fix is to answer it, not to loosen it.

  B. THE ADVISOR'S TESTS.  Removing the edge tab removed the only thing that opened the
     panel, so the panel renders nothing and eight tests that click a launcher now fail.
     They are not wrong about anything - they describe a control that was deliberately
     taken away.

     So the mount goes too, and the tests with it. What is NOT deleted is
     ``advisor-panel.tsx``: the briefing logic, the RBAC-aware empty states and the
     mark-read-on-close behaviour are all still good, and if the Advisor should live
     somewhere that is not a tab stuck to the side of every page, it is one line from
     coming back. Deleting the component would throw that away to tidy up a test run.

Both sections are idempotent and independent: each either applies completely or is
skipped and reported.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
NEW_TABLE = "ui_labels"

report: list[str] = []
skipped: list[str] = []

IMPORT_RE = re.compile(r'^import\s*\{([^}]*)\}\s*from\s*"([^"]+)";\s*$', re.M)


def window(text: str, needle: str, before: int = 3, after: int = 12) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found in this file)"


def matching_brace(text: str, open_at: int) -> int | None:
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


# ── A. the table inventory ─────────────────────────────────────────────────────────
def section_expected_tables() -> None:
    label = "table inventory"
    path = ROOT / "backend/tests/test_models_metadata.py"
    if not path.exists():
        skipped.append(f"[{label}] {path} does not exist here - nothing changed.")
        return
    text = path.read_text()
    if f'"{NEW_TABLE}"' in text:
        report.append(f"[{label}] {NEW_TABLE} already listed - left alone")
        return

    head = re.search(r"^EXPECTED_TABLES(?:\s*:\s*[^=\n]+)?\s*=\s*", text, re.M)
    if head is None:
        skipped.append(
            f"[{label}] {path}: no EXPECTED_TABLES to add to. Nothing changed.\n"
            + window(text, "EXPECTED_TABLES")
        )
        return
    open_at = text.find("{", head.end())
    close_at = matching_brace(text, open_at) if open_at != -1 else None
    if open_at == -1 or close_at is None:
        skipped.append(
            f"[{label}] {path}: EXPECTED_TABLES is not a brace-delimited literal, so where\n"
            "  to add the name is a guess. Nothing changed.\n" + window(text, "EXPECTED_TABLES")
        )
        return

    body = text[open_at + 1 : close_at]
    indent = "    "
    entries = re.findall(r"^(\s*)\"", body, re.M)
    if entries:
        indent = entries[-1]
    # Appended, not sorted in: the list follows the schema's own order, and re-sorting
    # it would make a one-line change look like a rewrite in the diff.
    addition = f'{indent}"{NEW_TABLE}",\n'
    text = text[: close_at].rstrip() + "\n" + addition + text[close_at:]
    path.write_text(text)
    report.append(f'[{label}] {path}: "{NEW_TABLE}" added to EXPECTED_TABLES')


# ── B. the advisor's mount and its tests ───────────────────────────────────────────
def strip_import(text: str, name: str) -> tuple[str, bool]:
    body = IMPORT_RE.sub("", text)
    if re.search(rf"\b{re.escape(name)}\b", body):
        return text, False
    for match in IMPORT_RE.finditer(text):
        names = [n.strip() for n in match.group(1).split(",") if n.strip()]
        if name not in names:
            continue
        kept = [n for n in names if n != name]
        if kept:
            line = f'import {{ {", ".join(kept)} }} from "{match.group(2)}";'
            return text[: match.start()] + line + text[match.end() :], True
        end = match.end()
        if end < len(text) and text[end] == "\n":
            end += 1
        return text[: match.start()] + text[end:], True
    return text, False


def section_advisor() -> None:
    label = "advisor"
    tests = sorted(ROOT.glob("frontend/tests/*advisor*"))
    mounts = [
        p
        for p in sorted(ROOT.glob("frontend/**/*.tsx"))
        if "node_modules" not in p.parts
        and ".next" not in p.parts
        and "tests" not in p.parts
        and "<AdvisorPanel" in p.read_text()
    ]

    if not tests and not mounts:
        report.append(f"[{label}] already retired - nothing mounted, no tests to remove")
        return

    for path in mounts:
        text = path.read_text()
        # Self-closing or paired, on its own line either way.
        pattern = re.compile(r"^[ \t]*<AdvisorPanel\b[^>]*(?:/>|>\s*</AdvisorPanel>)[ \t]*\n", re.M)
        hits = len(pattern.findall(text))
        if hits != 1:
            skipped.append(
                f"[{label}] {path}: expected exactly one <AdvisorPanel /> on its own line, "
                f"found {hits}. Nothing changed there.\n" + window(text, "<AdvisorPanel")
            )
            continue
        text = pattern.sub("", text, count=1)
        text, dropped = strip_import(text, "AdvisorPanel")
        path.write_text(text)
        report.append(
            f"[{label}] {path}: the panel is no longer mounted"
            + (" (import pruned)" if dropped else "")
        )

    for path in tests:
        # Only remove the tests once the launcher really is gone - otherwise this would
        # delete a suite that was about to start passing again.
        still_mounted = [
            p
            for p in sorted(ROOT.glob("frontend/**/*.tsx"))
            if "node_modules" not in p.parts
            and ".next" not in p.parts
            and "tests" not in p.parts
            and "<AdvisorPanel" in p.read_text()
        ]
        if still_mounted:
            skipped.append(
                f"[{label}] {path} kept: the panel is still mounted in "
                f"{', '.join(str(p) for p in still_mounted)}, so its tests may still be "
                "describing something real."
            )
            continue
        path.unlink()
        report.append(
            f"[{label}] {path} removed - it clicks a launcher that was deliberately taken "
            "away, so it can no longer pass and is no longer describing the product"
        )

    panel = [
        p
        for p in sorted(ROOT.glob("frontend/**/*advisor*.tsx"))
        if "node_modules" not in p.parts and "tests" not in p.parts
    ]
    if panel:
        report.append(
            f"[{label}] KEPT: {', '.join(str(p) for p in panel)} - the briefing itself is "
            "intact and unmounted, one line from coming back somewhere that is not a tab "
            "stuck to the edge of every page"
        )


def main() -> int:
    if not (ROOT / "backend").is_dir() or not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    section_expected_tables()
    section_advisor()

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

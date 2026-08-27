#!/usr/bin/env python3
"""Two small corrections to what the dashboard says and where it starts.

  A. "TF Profit" becomes "Gross Profit" everywhere it is shown. It is a display name,
     so this changes text and never an identifier: the underlying column stays
     ``rpt_tf_profit_usd``, which is what the metric registry, the BigQuery view and
     every saved report agree on. Renaming that would be a schema change wearing a
     label change's clothes.

     Found by searching rather than by anchor, because the phrase may appear on a card,
     in a picker, in a tooltip and in a column header, and a rename that reaches three
     of those four is worse than none - it makes the same number look like two metrics.
     Every site changed is listed.

  B. The default date range becomes THIS MONTH SO FAR - the 1st to today - instead of a
     rolling 30 days. The preset already exists ("mtd"); only which one is the default
     changes, so every other window is still one click away and saved views that pin a
     range are untouched.

Each section stands alone: one can apply while the other reports why it could not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
FILTERS = ROOT / "frontend/lib/filters.ts"

# Display spellings only. The identifier `rpt_tf_profit_usd` contains "tf_profit" and is
# deliberately NOT matched: it is the column name, not a label.
RENAMES = (("TF Profit", "Gross Profit"), ("TF profit", "Gross profit"))

NEW_PRESET = "mtd"
PRESET_RE = re.compile(
    r'(?P<head>const DEFAULT_PRESET: Exclude<DatePreset, "custom"> = ")(?P<value>[^"]+)(?P<tail>";)'
)
PRESET_COMMENT = """// Month-to-date, not a rolling window. The business is reported in calendar months,
// so the figure on the screen when the dashboard opens should be the one anybody would
// quote in a meeting: this month so far. A rolling 30 days spans two months and matches
// no report that gets filed. Every other window is still one click away in the picker,
// and a saved view that pins its own range is unaffected.
"""

report: list[str] = []
skipped: list[str] = []


def source_files() -> list[Path]:
    out: list[Path] = []
    for pattern in ("frontend/**/*.tsx", "frontend/**/*.ts", "backend/**/*.py"):
        for path in ROOT.glob(pattern):
            if {"node_modules", ".next", "__pycache__", ".venv"} & set(path.parts):
                continue
            if path.name.endswith(".d.ts"):
                continue
            out.append(path)
    return sorted(set(out))


def section_rename() -> None:
    hits = 0
    for path in source_files():
        text = path.read_text()
        if not any(old in text for old in (o for o, _ in RENAMES)):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for old, new in RENAMES:
                if old in line:
                    report.append(f'[label] {path}:{i}  "{old}" -> "{new}"')
                    hits += 1
        for old, new in RENAMES:
            text = text.replace(old, new)
        path.write_text(text)

    if not hits:
        report.append(
            '[label] no "TF Profit" anywhere under frontend/ or backend/ - either it is '
            "already renamed, or the heading is built from something other than that "
            "literal text. Nothing was changed."
        )


def section_default_range() -> None:
    if not FILTERS.exists():
        skipped.append(f"[default range] {FILTERS} is missing - the default is unchanged.")
        return
    text = FILTERS.read_text()

    match = PRESET_RE.search(text)
    if match is None or len(PRESET_RE.findall(text)) != 1:
        skipped.append(
            "[default range] expected exactly one `const DEFAULT_PRESET: "
            'Exclude<DatePreset, "custom"> = "..."` - nothing was changed.\n'
            + "\n".join(
                f"      | {ln}"
                for ln in text.splitlines()
                if "DEFAULT_PRESET" in ln or "DatePreset" in ln
            )
        )
        return

    if match.group("value") == NEW_PRESET:
        report.append(f'[default range] already "{NEW_PRESET}" - left alone')
        return

    # The preset must actually exist, or the default would produce a range for nothing.
    if f'"{NEW_PRESET}"' not in text:
        skipped.append(
            f'[default range] there is no "{NEW_PRESET}" preset in {FILTERS}, so making it '
            "the default would leave the picker with a value it cannot render. Nothing "
            "was changed."
        )
        return

    was = match.group("value")
    line_start = text.rfind("\n", 0, match.start()) + 1
    text = (
        text[:line_start]
        + PRESET_COMMENT
        + match.group("head")
        + NEW_PRESET
        + match.group("tail")
        + text[match.end() :]
    )
    FILTERS.write_text(text)
    report.append(
        f'[default range] {FILTERS}: default preset "{was}" -> "{NEW_PRESET}" '
        "(1st of this month → today)"
    )


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    section_rename()
    section_default_range()

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

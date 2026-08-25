#!/usr/bin/env python3
"""Restore the two theme tokens a past patch destroyed, and stop the test hiding the next one.

WHAT HAPPENED. An earlier accessibility fix darkened some colours for contrast, but in two
themes it wrote its corrected line on top of a DIFFERENT token's line instead of replacing
its own. The fix landed; an unrelated token was destroyed in the same stroke. The audit
(scripts/theme-token-audit.py) shows the fingerprint in both places - a token defined
twice, sitting exactly where the missing one should be:

  colorblind: --color-positive defined twice, --color-negative gone entirely
  rose:       --color-text-* line duplicated, --color-accent gone entirely

An absent token is not a blank; it inherits the base :root value, which belongs to the
DARK theme. So the colourblind theme - the one that exists for accessibility - has been
painting negative numbers in a dark-theme red on a light background, and rose has been
doing the same with its accent. Neither raises an error anywhere.

WHY THE TEST DID NOT CATCH IT. tests/contrast.test.ts skipped any pair where a token was
missing. The single case that most needed reporting was the one it stayed silent about,
which is why this shipped and sat there. That skip becomes a failure here: a theme that
does not define a semantic colour fails, and says so by name.

THE COLOURS. Both replacements keep their palette's identity and are computed, not
eyeballed. colorblind gets the Okabe-Ito vermillion darkened to clear AA (#b34e00: 4.76:1
on the app background, 5.24:1 on cards) while staying 1.37 apart in luminance from the
positive green - above the 1.30 the delta test requires, though not by much, and that is
inherent: both colours must clear 4.5:1 on a LIGHT background, which confines them to a
narrow luminance band. Buying more margin means moving the positive too, which is a design
decision for the owner, not a thing to slip into a fix. rose gets an accent in its own
family, darkened until it clears AA (#b03f5c: 5.25:1 and 5.55:1).

The script verifies its own output: it re-parses the patched file, re-runs the WCAG maths
over every theme, and refuses to write if any theme is still missing a semantic token or
any pair still falls below AA.

    python3 scripts/fix-theme-tokens.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

THEME_CSS = Path("frontend/app/theme.css")
CONTRAST_TEST = Path("frontend/tests/contrast.test.ts")

AA = 4.5
FOREGROUNDS = (
    "--color-text-primary",
    "--color-text-secondary",
    "--color-text-muted",
    "--color-accent",
    "--color-positive",
    "--color-negative",
)
SURFACES = ("--color-bg-app", "--color-bg-card")

BLOCK = re.compile(r'(:root(?:\[data-theme="[^"]+"\])?|html\[[^\]]+\])\s*\{([^}]*)\}')
TOKEN = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+)")

EDITS = [
    {
        "path": THEME_CSS,
        "why": "colorblind: the duplicated positive line was the negative line",
        "anchor": (
            "  --color-positive:#009e73; --color-positive-soft:rgba(0,158,115,.13);\n"
            "  --color-positive:#006449; --color-positive-soft:rgba(0,158,115,.13);\n"
        ),
        "replacement": (
            "  --color-positive:#006449; --color-positive-soft:rgba(0,158,115,.13);\n"
            "  --color-negative:#b34e00; --color-negative-soft:rgba(179,78,0,.13);\n"
        ),
        "marker": "--color-negative:#b34e00;",
    },
    {
        "path": THEME_CSS,
        "why": "rose: the duplicated text line was the accent line",
        "anchor": (
            "  --color-text-primary:#2a1e1e; --color-text-secondary:#6b5555;"
            " --color-text-muted:#9a8383;\n"
            "  --color-text-primary:#2a1e1e; --color-text-secondary:#6b5555;"
            " --color-text-muted:#826a6a;\n"
        ),
        "replacement": (
            "  --color-text-primary:#2a1e1e; --color-text-secondary:#6b5555;"
            " --color-text-muted:#826a6a;\n"
            "  --color-accent:#b03f5c; --color-accent-strong:#93314b;"
            " --color-accent-soft:rgba(176,63,92,.13);\n"
        ),
        "marker": "--color-accent:#b03f5c;",
    },
    {
        "path": CONTRAST_TEST,
        "why": "a missing semantic token must fail, not be skipped",
        "anchor": """      for (const fg of FOREGROUNDS) {
        for (const bg of SURFACES) {
          const foreground = theme.tokens[fg];
          const background = theme.tokens[bg];
          if (!foreground || !background) continue;
          const ratio = contrast(foreground, background);""",
        "replacement": """      for (const fg of FOREGROUNDS) {
        const foreground = theme.tokens[fg];
        if (!foreground) {
          // Skipping this, as this test used to, is precisely how the colourblind theme
          // shipped with no --color-negative at all. An absent token is not blank - it
          // inherits the base :root value, designed for a different background - and
          // nothing anywhere raises an error. A missing semantic colour is a failure.
          failures.push(`${fg} is not defined by this theme (inherited from :root)`);
          continue;
        }
        for (const bg of SURFACES) {
          const background = theme.tokens[bg];
          if (!background) continue;
          const ratio = contrast(foreground, background);""",
        "marker": "is not defined by this theme (inherited from :root)",
    },
]


def luminance(value: str) -> float | None:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", value.strip())
    if not match:
        return None
    digits = match.group(1)
    channels = [int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(a: str, b: str) -> float | None:
    la, lb = luminance(a), luminance(b)
    if la is None or lb is None:
        return None
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def audit(css: str) -> list[str]:
    """Every reason the patched stylesheet would still fail the contrast test."""
    problems: list[str] = []
    for match in BLOCK.finditer(css):
        name = match.group(1)
        tokens = {n: v.strip() for n, v in TOKEN.findall(match.group(2))}
        if not tokens.get("--color-bg-app") or not tokens.get("--color-text-primary"):
            continue  # not a theme the contrast test considers
        for fg in FOREGROUNDS:
            value = tokens.get(fg)
            if not value:
                problems.append(f"{name}: {fg} is still missing")
                continue
            for bg in SURFACES:
                surface = tokens.get(bg)
                if not surface:
                    continue
                found = ratio(value, surface)
                if found is not None and found < AA:
                    problems.append(
                        f"{name}: {fg} ({value}) on {bg} ({surface}) = {found:.2f}:1"
                    )
        if "colorblind" in name:
            positive, negative = tokens.get("--color-positive"), tokens.get("--color-negative")
            separation = ratio(positive, negative) if positive and negative else None
            if separation is None or separation <= 1.3:
                problems.append(
                    f"{name}: positive/negative separation "
                    f"{separation if separation is None else round(separation, 2)} is not above 1.3"
                )
    return problems


def resolve(text: str, anchor: str, replacement: str, marker: str):
    """The deployment normalises em-dashes; flatten anchor, replacement and marker together
    or the patch reintroduces the character the file was cleaned of."""
    if anchor in text:
        return anchor, replacement, marker
    flat = anchor.replace("—", "-")
    if flat != anchor and flat in text:
        return flat, replacement.replace("—", "-"), marker.replace("—", "-")
    return anchor, replacement, marker


def main() -> int:
    if not THEME_CSS.exists():
        print(f"ABORTED: {THEME_CSS} not found - run from the repository root")
        return 1

    planned: dict[Path, str] = {}
    problems: list[str] = []
    skipped: list[str] = []
    for index, edit in enumerate(EDITS, start=1):
        path = edit["path"]
        if not path.exists():
            problems.append(f"  [{index}] {path}: file not found")
            continue
        text = planned.get(path, path.read_text())
        anchor, replacement, marker = resolve(
            text, edit["anchor"], edit["replacement"], edit["marker"]
        )
        if marker in text:
            skipped.append(f"{path} [{index}]: already applied")
            continue
        found = text.count(anchor)
        if found != 1:
            problems.append(
                f"  [{index}] {path}: expected exactly 1 match, found {found}"
                f"\n        ({edit['why']})"
                f"\n        anchor starts: {anchor.splitlines()[0].strip()[:76]!r}"
            )
            continue
        planned[path] = text.replace(anchor, replacement, 1)

    if problems:
        print("ABORTED - NOTHING was written:")
        print()
        for problem in problems:
            print(problem)
        print()
        print("Run scripts/theme-token-audit.py to see what is actually in the file.")
        return 1

    if not planned:
        print("nothing to do - already applied")
        return 0

    # Verify the OUTPUT. Writing colours without re-running the maths over them would be
    # trusting the same arithmetic that produced the bug this script exists to fix.
    remaining = audit(planned.get(THEME_CSS, THEME_CSS.read_text()))
    if remaining:
        print("ABORTED - NOTHING was written. The patched stylesheet still fails:")
        print()
        for problem in remaining:
            print(f"  {problem}")
        return 1

    for path, content in sorted(planned.items(), key=lambda pair: str(pair[0])):
        path.write_text(content)
        print(f"wrote {path}")
    for note in skipped:
        print(f"skip  {note}")
    print()
    print("Every theme now defines all six semantic colours and every pair clears AA 4.5:1.")
    print("A theme that drops one in future FAILS the contrast test instead of skipping it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

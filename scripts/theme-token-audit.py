#!/usr/bin/env python3
"""Read-only audit of theme.css: which themes are missing tokens, and which define one twice.

WHY THIS EXISTS. The colourblind theme crashes the contrast test because it has no
--color-negative at all - and, tellingly, it defines --color-positive TWICE. That is the
fingerprint of an earlier patch writing a corrected line ON TOP of a different token's
line instead of replacing its own: the fix landed, and an unrelated token was destroyed
in the same stroke. Where that happened once it can have happened elsewhere, and a theme
that silently inherits a DARK theme's colour onto a LIGHT background is unreadable
without ever raising an error.

The contrast test cannot find this. It does `if (!foreground || !background) continue`,
so a token that is missing is skipped rather than failed - the one case that most needs
reporting is the one case it stays quiet about.

This changes NOTHING. It prints, per theme: tokens defined more than once (with every
value, since only the last one wins), and tokens other themes define but this one does
not. Non-hex values (rgba/hsl) are counted as present, because the point is what the
theme DEFINES, not what a regex happens to recognise.

    python3 scripts/theme-token-audit.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

THEME_CSS = Path("frontend/app/theme.css")

BLOCK = re.compile(r'(:root(?:\[data-theme="[^"]+"\])?|html\[[^\]]+\])\s*\{([^}]*)\}')
TOKEN = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+)")

# Tokens that carry body-sized text or a semantic meaning a theme must own. A theme that
# leaves one of these to the base :root inherits a colour designed for a different
# background - which is exactly how an unreadable combination ships unnoticed.
SEMANTIC = (
    "--color-text-primary",
    "--color-text-secondary",
    "--color-text-muted",
    "--color-accent",
    "--color-positive",
    "--color-negative",
    "--color-bg-app",
    "--color-bg-card",
)


def luminance(value: str) -> float | None:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", value.strip())
    if not match:
        return None
    digits = match.group(1)
    channels = [int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float | None:
    la, lb = luminance(a), luminance(b)
    if la is None or lb is None:
        return None
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def main() -> int:
    if not THEME_CSS.exists():
        print(f"ABORTED: {THEME_CSS} not found - run from the repository root")
        return 1
    css = THEME_CSS.read_text()

    themes: list[tuple[str, dict[str, list[str]]]] = []
    for match in BLOCK.finditer(css):
        tokens: dict[str, list[str]] = {}
        for name, value in TOKEN.findall(match.group(2)):
            tokens.setdefault(name, []).append(value.strip())
        if tokens:
            themes.append((match.group(1), tokens))
    if not themes:
        print("ABORTED: parsed no theme blocks - the file shape has changed")
        return 1

    print(f"{len(themes)} theme blocks parsed from {THEME_CSS}")
    print()

    defined_somewhere = {name for _, tokens in themes for name in tokens}
    problems = 0

    for name, tokens in themes:
        duplicates = {k: v for k, v in tokens.items() if len(v) > 1}
        # Only report a token as missing if it is one the themes generally carry.
        missing = [
            token
            for token in SEMANTIC
            if token in defined_somewhere and token not in tokens
        ]
        if not duplicates and not missing:
            continue
        problems += 1
        print(f"--- {name}")
        for token, values in sorted(duplicates.items()):
            # CSS takes the last one; the earlier line is dead, and whatever was meant to
            # be on that line is gone.
            print(f"    DUPLICATE {token}: {' | '.join(values)}   (only {values[-1]!r} applies)")
        for token in missing:
            print(f"    MISSING   {token}  - inherited from the base :root")
        # Where both a surface and a foreground are present, show what it actually is.
        app = tokens.get("--color-bg-app", [""])[-1]
        for fg in ("--color-positive", "--color-negative", "--color-accent"):
            value = tokens.get(fg, [""])[-1]
            ratio = contrast(value, app) if value and app else None
            if ratio is not None and ratio < 4.5:
                print(f"    LOW       {fg} ({value}) on {app} = {ratio:.2f}:1  (AA needs 4.5)")
        print()

    if problems == 0:
        print("No duplicated or missing semantic tokens in any theme.")
    else:
        print(f"{problems} theme(s) need attention. Nothing was changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

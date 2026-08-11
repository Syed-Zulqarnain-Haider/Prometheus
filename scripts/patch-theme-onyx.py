#!/usr/bin/env python3
"""Re-grade the dashboard to the reference video's palette (frontend/app/theme.css).

Measured, not eyeballed: every colour below comes from docs/BRAND-PALETTE.md, which was
built by quantising eight frames of the reference clip.

This patches the DEPLOYED theme.css in place rather than shipping a whole file, because
that file carries nine themes and the font-preference blocks that this tree does not have.
Every anchor must match exactly once or nothing is written.

What changes:
  * `:root` (the default dark theme)      -> black canvas + green surfaces + mint accent
  * `:root[data-theme="light"]`           -> near-white canvas + deep-green accent
  * radius tokens                         -> pills and 20px cards, as in the reference
  * display font                          -> grotesk (the reference sets headings in sans)

What is preserved:
  * The previous warm "Swiss Ledger" palette is appended as `:root[data-theme="ledger"]`,
    so nothing is lost and it can be selected back.
  * Every other theme, the font-size/family blocks, spacing, motion: untouched.

Run:  python3 scripts/patch-theme-onyx.py
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

TARGET = Path("frontend/app/theme.css")
MARKER = 'data-theme="ledger"'  # proves the patch already ran

# (anchor, replacement). Anchors are single lines lifted verbatim from the deployed file.
# The spaced formatting is unique to the :root and light blocks - the other themes are
# written compactly - so each of these matches exactly one line.
REPLACEMENTS: list[tuple[str, str]] = [
    # ── DARK (:root) surfaces: black canvas, green-tinted elevation ──────────────
    ("  --color-bg-app:        #14110b;", "  --color-bg-app:        #0a0a0a;"),
    ("  --color-bg-sidebar:    #100d08;", "  --color-bg-sidebar:    #050505;"),
    ("  --color-bg-card:       #1c1810;", "  --color-bg-card:       #171717;"),
    ("  --color-bg-card-sunken:#161109;", "  --color-bg-card-sunken:#101010;"),
    ("  --color-bg-elevated:   #271f14;", "  --color-bg-elevated:   #1e2120;"),
    # strokes
    ("  --color-border:        #2d2618;", "  --color-border:        #242927;"),
    ("  --color-border-strong: #3f3624;", "  --color-border-strong: #3a4341;"),
    ("  --color-border-faint:  #221c11;", "  --color-border-faint:  #1a1d1c;"),
    # text
    ("  --color-text-primary:   #f1ead8;", "  --color-text-primary:   #fcfcfc;"),
    ("  --color-text-secondary: #a99f86;", "  --color-text-secondary: #bcc4c2;"),
    ("  --color-text-muted:     #766c57;", "  --color-text-muted:     #7d8683;"),
    # accent: the mint CTA band, #8fbcaf (23.7% of the closing frame)
    ("  --color-accent:        #cb5d50;", "  --color-accent:        #8fbcaf;"),
    ("  --color-accent-strong: #b8473c;", "  --color-accent-strong: #a8cec3;"),
    (
        "  --color-accent-soft:   rgba(203, 93, 80, 0.15);",
        "  --color-accent-soft:   rgba(143, 188, 175, 0.16);",
    ),
    (
        "  --color-accent-foreground: #1c1810; /* readable text on the accent fill */",
        "  --color-accent-foreground: #0a0a0a; /* dark text on the mint fill, as the reference does */",
    ),
    ("  --color-brand:         #cb5d50;", "  --color-brand:         #8fbcaf;"),
    # status colours: positive stays green but is pushed away from the mint accent so a
    # rising figure never reads as "branded"; negative keeps the warm red.
    ("  --color-positive:      #6faa7e;", "  --color-positive:      #5fc79b;"),
    (
        "  --color-positive-soft: rgba(111, 170, 126, 0.15);",
        "  --color-positive-soft: rgba(95, 199, 155, 0.15);",
    ),
    ("  --color-negative:      #d4564b;", "  --color-negative:      #e0736b;"),
    (
        "  --color-negative-soft: rgba(212, 86, 75, 0.14);",
        "  --color-negative-soft: rgba(224, 115, 107, 0.15);",
    ),
    # ── DARK chart ramp: brand mint first, then deliberately distinct hues ───────
    ("  --chart-bar:           #cb5d50;", "  --chart-bar:           #8fbcaf;"),
    ("  --chart-bar-2:         #3c3420;", "  --chart-bar-2:         #25302d;"),
    ("  --chart-spark:         #6faa7e;", "  --chart-spark:         #5fc79b;"),
    ("  --chart-spark-cash:    #a886bf;", "  --chart-spark-cash:    #a9b9d6;"),
    ("  --chart-target:        #8a7f66;", "  --chart-target:        #7d8683;"),
    ("  --chart-grid:          #251e12;", "  --chart-grid:          #1c1f1e;"),
    ("  --chart-line-cpi:      #d8a94e;", "  --chart-line-cpi:      #d8b98f;"),
    ("  --chart-grad-from:     #cb5d50;", "  --chart-grad-from:     #8fbcaf;"),
    ("  --chart-grad-to:       #a886bf;", "  --chart-grad-to:       #3a5752;"),
    # ── Type + radius: the reference sets headings in a grotesk, and rounds hard ──
    (
        '  --font-display: "Spectral", Georgia, "Times New Roman", serif;',
        '  --font-display: "Archivo", ui-sans-serif, system-ui, -apple-system, sans-serif;',
    ),
    ("  --ls-tight: -0.01em;", "  --ls-tight: -0.02em;"),
    ("  --radius-card:  10px;", "  --radius-card:  20px;"),
    ("  --radius-inner: 8px;", "  --radius-inner: 14px;"),
    ("  --radius-chip:  6px;", "  --radius-chip:  9999px;"),
    # ── LIGHT theme: the reference's editorial band (#fcfcfc on #121313) ─────────
    ("  --color-bg-app:        #f3f0e7;", "  --color-bg-app:        #f4f6f5;"),
    ("  --color-bg-sidebar:    #f8f6ef;", "  --color-bg-sidebar:    #fcfcfc;"),
    ("  --color-bg-card:       #fbfaf4;", "  --color-bg-card:       #fcfcfc;"),
    ("  --color-bg-card-sunken:#efebdf;", "  --color-bg-card-sunken:#f0f2f1;"),
    ("  --color-bg-elevated:   #ebe6d7;", "  --color-bg-elevated:   #e9ecea;"),
    ("  --color-border:        #e1dccd;", "  --color-border:        #e4e6e6;"),
    ("  --color-border-strong: #ccc5b1;", "  --color-border-strong: #c9cfcd;"),
    ("  --color-border-faint:  #ebe6d8;", "  --color-border-faint:  #eef0ef;"),
    ("  --color-text-primary:   #1f1d17;", "  --color-text-primary:   #121313;"),
    ("  --color-text-secondary: #6c6757;", "  --color-text-secondary: #55605c;"),
    ("  --color-text-muted:     #9a9485;", "  --color-text-muted:     #8a938f;"),
    # The mint fails contrast as text on white, so on light the accent is the deep green
    # from the reference's Forex card and the mint becomes a fill only.
    ("  --color-accent:        #8a2f2f;", "  --color-accent:        #3a5752;"),
    ("  --color-accent-strong: #6f2525;", "  --color-accent-strong: #2b433f;"),
    (
        "  --color-accent-soft:   rgba(138, 47, 47, 0.10);",
        "  --color-accent-soft:   rgba(58, 87, 82, 0.10);",
    ),
    ("  --color-accent-foreground: #fbfaf4;", "  --color-accent-foreground: #fcfcfc;"),
    ("  --color-brand:         #8a2f2f;", "  --color-brand:         #3a5752;"),
    ("  --chart-bar:           #8a2f2f;", "  --chart-bar:           #3a5752;"),
    ("  --chart-bar-2:         #ddd6c5;", "  --chart-bar-2:         #dfe4e2;"),
    ("  --chart-grid:          #e8e3d6;", "  --chart-grid:          #e8ebea;"),
    ("  --chart-grad-from:     #8a2f2f;", "  --chart-grad-from:     #3a5752;"),
    ("  --chart-grad-to:       #6b4a78;", "  --chart-grad-to:       #8fbcaf;"),
]

# The previous default palette, kept selectable so the re-grade is reversible.
LEDGER_BLOCK = """
/* ---- LEDGER - the previous default ("Swiss Ledger" warm charcoal), kept so the
   re-grade to the reference palette is reversible rather than destructive. ------ */
:root[data-theme="ledger"] {
  --color-bg-app:#14110b; --color-bg-sidebar:#100d08; --color-bg-card:#1c1810;
  --color-bg-card-sunken:#161109; --color-bg-elevated:#271f14;
  --color-border:#2d2618; --color-border-strong:#3f3624; --color-border-faint:#221c11;
  --color-text-primary:#f1ead8; --color-text-secondary:#a99f86; --color-text-muted:#766c57;
  --color-accent:#cb5d50; --color-accent-strong:#b8473c; --color-accent-soft:rgba(203,93,80,.15);
  --color-accent-foreground:#1c1810; --color-brand:#cb5d50;
  --color-positive:#6faa7e; --color-positive-soft:rgba(111,170,126,.15);
  --color-negative:#d4564b; --color-negative-soft:rgba(212,86,75,.14);
  --color-purple:#a886bf; --color-purple-soft:rgba(168,134,191,.16);
  --color-amber:#d8a94e; --color-amber-soft:rgba(216,169,78,.15);
  --color-orange:#cf8551; --color-orange-soft:rgba(207,133,81,.15);
  --color-cat-game:#c08a6a; --color-cat-health:#6faa7e; --color-cat-finance:#a886bf; --color-cat-lifestyle:#d8a94e;
  --chart-bar:#cb5d50; --chart-bar-2:#3c3420; --chart-spark:#6faa7e; --chart-spark-cash:#a886bf;
  --chart-target:#8a7f66; --chart-grid:#251e12; --chart-line-cpi:#d8a94e;
  --chart-grad-from:#cb5d50; --chart-grad-to:#a886bf;
  --font-display: "Spectral", Georgia, "Times New Roman", serif;
  --radius-card:10px; --radius-inner:8px; --radius-chip:6px;
  --shadow-card:0 12px 30px -12px rgba(0,0,0,.62),0 3px 10px -3px rgba(0,0,0,.42);
  --shadow-pop:0 18px 40px -10px rgba(0,0,0,.6);
}
"""


def main() -> None:
    if not TARGET.exists():
        print(f"ABORTED: {TARGET} not found - run from the repository root.", file=sys.stderr)
        raise SystemExit(1)

    text = TARGET.read_text()

    if MARKER in text:
        print(f"skipped  {TARGET} (already re-graded)")
        return

    # Pass 1: verify every anchor before touching anything.
    problems = [
        f"{text.count(old)}x  {old.strip()}" for old, _ in REPLACEMENTS if text.count(old) != 1
    ]
    if problems:
        print("ABORTED: these anchors did not match exactly once:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        print("Nothing was written; theme.css is untouched.", file=sys.stderr)
        raise SystemExit(1)

    # Pass 2: apply.
    backup = TARGET.with_suffix(f".css.bak.{int(time.time())}")
    shutil.copy2(TARGET, backup)
    for old, new in REPLACEMENTS:
        text = text.replace(old, new, 1)
    text = text.rstrip("\n") + "\n" + LEDGER_BLOCK

    TARGET.write_text(text)
    print(f"patched  {TARGET}  ({len(REPLACEMENTS)} tokens re-graded)")
    print(f"backup   {backup}")
    print("The previous palette is still available as data-theme=\"ledger\".")


if __name__ == "__main__":
    main()

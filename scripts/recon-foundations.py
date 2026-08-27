#!/usr/bin/env python3
"""Read-only. The files F1 (metric registry) and F2 (formatting) must be built from.

The spec says build the foundations first and 'do not invent product behaviour'. Both
already have partial implementations here - report-metrics.ts, format.ts, the backend
metric registry, the glossary - so the job is to EXTEND one source, not add a third.
This dumps exactly what is needed to do that, and nothing else.

Writes nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
BE = ROOT / "backend"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def dump(path: Path, cap: int = 260, first: int = 1) -> None:
    if not path.exists():
        print(f"\n--- {path}: MISSING")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    last = min(first + cap - 1, len(lines))
    print(f"\n--- {path.relative_to(ROOT)}  [{first}-{last} of {len(lines)}]")
    for number in range(first, last + 1):
        print(f"{number:5}: {lines[number - 1]}")


def hits(path: Path, pattern: str, limit: int = 60) -> None:
    if not path.exists():
        print(f"\n--- {path}: MISSING")
        return
    print(f"\n--- {path.relative_to(ROOT)}  (/{pattern}/)")
    shown = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, line) and shown < limit:
            print(f"  {number:5}: {line.rstrip()}")
            shown += 1


# ── F1: what already claims to be the metric source of truth ─────────────────
rule("F1a. frontend/lib/report-metrics.ts - the existing metric list")
dump(FE / "lib" / "report-metrics.ts")

rule("F1b. backend metric registry - shape, groups, and the reported/modeled split")
registry = BE / "app" / "core" / "metric_registry.py"
hits(registry, r"^class |^@|^\s*(name|group|pg_type|label|additive|description)\s*[:=]", limit=40)
hits(registry, r"rpt_", limit=40)
hits(registry, r'group\s*=\s*"|Group\.', limit=40)

rule("F1c. every metric label currently hand-typed in JSX (the F1 'done when')")
labels = re.compile(r'label:\s*"[^"]+"|>\s*(Revenue|Spend|Profit|Installs|ROAS|CPI|Net Rev|Gross Rev)')
for path in sorted(FE.rglob("*.tsx")):
    if any(part in path.parts for part in ("node_modules", ".next")):
        continue
    found = [
        (n, line.strip())
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if labels.search(line)
    ]
    if found:
        print(f"\n{path.relative_to(ROOT)}")
        for number, line in found[:12]:
            print(f"  {number:5}: {line[:120]}")
        if len(found) > 12:
            print(f"        ... {len(found) - 12} more")

# ── F2: what formatting already exists ───────────────────────────────────────
rule("F2a. frontend/lib/format.ts - the existing formatters")
dump(FE / "lib" / "format.ts")

rule("F2b. every date format in use (F2 says there must be exactly one)")
for path in sorted(list(FE.rglob("*.ts")) + list(FE.rglob("*.tsx"))):
    if any(part in path.parts for part in ("node_modules", ".next")):
        continue
    found = [
        (n, line.strip())
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r'format\(.*["\'][dMyHhms/\- ]{3,}["\']|toLocaleDateString|yyyy-MM-dd|MMM d', line)
    ]
    if found:
        print(f"\n{path.relative_to(ROOT)}")
        for number, line in found[:8]:
            print(f"  {number:5}: {line[:120]}")

# ── P0-1 evidence: where the two families collide ────────────────────────────
rule("P0-1. the surfaces the audit caught disagreeing")
hits(FE / "components" / "compare" / "compare-client.tsx", r"label|title|metric|rpt_", limit=45)

rule("F6. the glossary as it stands")
dump(FE / "app" / "(app)" / "glossary" / "page.tsx", cap=120)

rule("NAV ORDER. why a reordered sidebar does not stay reordered")
print("""  The order is written to localStorage keyed by user id. localStorage is PER
  BROWSER: a different browser, a different machine, a private window, or cleared
  site data and the arrangement is gone - it was never on the account.

  Dashboard layouts are already persisted server-side per user, so the mechanism
  exists and the nav simply never used it. Three things to confirm:

    a) is the write actually reached, and is the key stable? (`me.user_id` was
       trimmed out of /me recently - if it is now undefined the key still works,
       but only by accident.)
    b) does grouping override it? The reorder is applied BEFORE grouping, so a
       move across sections has no lasting visual effect - the item snaps back
       into its own group, which looks exactly like "it did not save".
    c) what does the existing per-user layout endpoint look like, so nav order
       can use the same one instead of inventing a second mechanism.
""")
dump(FE / "components" / "layout" / "sidebar.tsx", cap=210)

print("\n-- (a)/(b) the order + grouping logic --")
hits(FE / "components" / "layout" / "sidebar.tsx",
     r"ORDER_KEY|localStorage|setOrder|applyOrder|groupItems|move\(|orderKey|user_id")

print("\n-- (c) the per-user preference endpoints that already exist --")
for path in (FE / "lib" / "api-hooks.ts", ROOT / "backend" / "app" / "api" / "v1" / "layouts.py",
             ROOT / "backend" / "app" / "api" / "v1" / "profile.py"):
    hits(path, r"layout|preference|column.?order|nav|PUT|POST|@router")

print("\n-- what /me actually returns now (the key depends on it) --")
hits(ROOT / "backend" / "app" / "api" / "v1" / "auth.py", r"def me|user_id|class MeOut|response_model")
hits(ROOT / "backend" / "app" / "schemas" / "auth.py", r"class .*Out|user_id|uid")

print("\nread-only: nothing was written.")

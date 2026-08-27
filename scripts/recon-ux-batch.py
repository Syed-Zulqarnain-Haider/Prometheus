#!/usr/bin/env python3
"""Read-only: the five UX items, and the traps in three of them.

  1. Overview widget order (Pod Owner -> HOU -> Top Apps). TRAP: the order is a
     per-user SAVED layout. Changing the default moves nothing for anyone who has
     already dragged their blocks - their saved order wins. Need to see whether the
     layout is versioned, or the change is invisible to exactly the person asking.
  2. Refresh landing on the same section. Which surfaces keep state in the URL and
     which keep it in a useState that a reload throws away.
  3. Updating on click rather than on refresh. Every mutation that does NOT
     invalidate its query afterwards - that is the whole bug, listed.
  4. The "Magnetic dot" control on the profile page.
  5. The glossary, in full, so it can be rewritten in plain language.

Writes nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
BE = ROOT / "backend"
SKIP = ("node_modules", ".next")


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def files(*patterns: str) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        out += [p for p in FE.rglob(pattern) if not any(s in p.parts for s in SKIP)]
    return sorted(set(out))


def dump(path: Path, cap: int = 200) -> None:
    if not path.exists():
        print(f"\n--- {path}: MISSING")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    print(f"\n--- {path.relative_to(ROOT)}  [1-{min(cap, len(lines))} of {len(lines)}]")
    for number, line in enumerate(lines[:cap], 1):
        print(f"{number:5}: {line}")


def scan(paths: list[Path], pattern: str, context: int = 0, limit: int = 120) -> None:
    regex = re.compile(pattern)
    shown = 0
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for index, line in enumerate(lines):
            if not regex.search(line) or shown >= limit:
                continue
            shown += 1
            print(f"\n{path.relative_to(ROOT)}:{index + 1}")
            for number in range(max(0, index - context), min(len(lines), index + context + 1)):
                mark = ">" if number == index else " "
                print(f"  {mark} {number + 1:5}: {lines[number].rstrip()[:150]}")
    if shown == 0:
        print("  (no matches)")


TS = files("*.ts", "*.tsx")

# ── 1 ────────────────────────────────────────────────────────────────────────
rule("1. Overview widget order - and whether a saved layout overrides the default")
dump(FE / "lib" / "overview-layout.ts", cap=160)
print("\n-- where the default order is consumed, and how a saved layout is merged --")
scan([FE / "components" / "overview" / "overview-client.tsx"],
     r"OVERVIEW_ITEM|layout|order|hidden|withHidden|useLayout|dashboard_layout|version", context=3)
print("\n-- the saved-layout endpoint: is it versioned? --")
scan([BE / "app" / "api" / "v1" / "layouts.py"], r".*", limit=90)

# ── 2 ────────────────────────────────────────────────────────────────────────
rule("2. what survives a refresh, and what does not")
print("-- state kept in the URL (survives refresh) --")
scan(TS, r"useSearchParams|searchParams\.get|router\.(push|replace)\(", context=2, limit=60)
print("\n-- tab state kept in useState (a reload throws it away) --")
scan(TS, r"useState.*[Tt]ab|activeTab|setTab|\?tab=", context=3, limit=50)

# ── 3 ────────────────────────────────────────────────────────────────────────
rule("3. mutations that do NOT refresh what they changed")
print("""  A useMutation with no onSuccess invalidateQueries leaves the screen showing the
  old value until something else refetches it - which is exactly "it only updates
  when I refresh". Listed per hook.
""")
for path in TS:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "useMutation" not in text:
        continue
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "useMutation" not in line:
            continue
        window = "\n".join(lines[index:index + 22])
        ok = "invalidateQueries" in window or "setQueryData" in window or "refetch" in window
        name = "?"
        for back in range(index, max(0, index - 8), -1):
            match = re.search(r"export function (\w+)", lines[back])
            if match:
                name = match.group(1)
                break
        verdict = "refreshes" if ok else "*** does NOT refresh anything ***"
        print(f"  {str(path.relative_to(ROOT)):46}:{index + 1:<5} {name:34} {verdict}")

print("\n-- how stale data is allowed to be --")
scan(TS, r"staleTime|refetchInterval|refetchOnWindowFocus|gcTime|cacheTime", context=1, limit=40)

# ── 4 ────────────────────────────────────────────────────────────────────────
rule("4. the 'Magnetic dot' control, and what else lives beside it")
scan(TS, r"[Mm]agnetic|cursor|ClickSpark|BackgroundFx|appearance|effect", context=8, limit=60)

# ── 5 ────────────────────────────────────────────────────────────────────────
rule("5. the glossary, in full")
dump(FE / "app" / "(app)" / "glossary" / "page.tsx", cap=400)
print("\n-- any other definition text that would have to agree with it --")
scan(TS, r"definition|description:\s*\"|InfoTooltip", limit=60)

print("\nread-only: nothing was written.")

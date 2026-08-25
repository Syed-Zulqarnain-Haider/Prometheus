#!/usr/bin/env python3
"""Read-only. Everything the next two changes need, in one pass.

  A. Daily moving average on the KPI cards - the card and the row that feeds it.
  B. Pod table keyed on POD OWNER, clickable through to that owner's full picture -
     the existing table, the /hou/[hou] page it should mirror, the pod-owner
     endpoints that already exist, and whether pod_owner is a filterable dimension.

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


def dump(path: Path, cap: int = 240, first: int = 1) -> None:
    if not path.exists():
        print(f"\n--- {path}: MISSING")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    last = min(first + cap - 1, len(lines))
    print(f"\n--- {path.relative_to(ROOT)}  [{first}-{last} of {len(lines)}]")
    for number in range(first, last + 1):
        print(f"{number:5}: {lines[number - 1]}")


def hits(path: Path, pattern: str, context: int = 0) -> None:
    if not path.exists():
        print(f"\n--- {path}: MISSING")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    regex = re.compile(pattern)
    print(f"\n--- {path.relative_to(ROOT)}  (/{pattern}/)")
    for index, line in enumerate(lines):
        if regex.search(line):
            for number in range(max(0, index - context), min(len(lines), index + context + 1)):
                mark = ">" if number == index else " "
                print(f"  {mark} {number + 1:5}: {lines[number]}")


# ── A. the KPI cards ─────────────────────────────────────────────────────────
rule("A1. the KPI card")
dump(FE / "components" / "overview" / "kpi-card.tsx")

rule("A2. the KPI row that feeds it")
dump(FE / "components" / "overview" / "kpi-row.tsx")

rule("A3. the moving-average helper and the sparkline helpers")
dump(FE / "lib" / "moving-average.ts", cap=80)
hits(FE / "lib" / "chart-helpers.ts", r"^export (function|const)")

# ── B. pod owner ─────────────────────────────────────────────────────────────
rule("B1. the pod table as it stands")
dump(FE / "components" / "overview" / "pod-table.tsx")

rule("B2. /hou/[hou] - the per-entity drill page this should mirror")
dump(FE / "app" / "(app)" / "hou" / "[hou]" / "page.tsx")

rule("B3. the existing pod-owner table")
dump(FE / "components" / "pod-owners" / "pod-owner-table.tsx", cap=140)

rule("B4. is pod_owner a filterable dimension server-side?")
hits(BE / "app" / "schemas" / "metrics.py", r"class MetricFilters|pod|hou|publisher|owner", context=1)
hits(BE / "app" / "services" / "query_builder.py", r"_GROUP_BY_COLUMN|pod_owner", context=1)

rule("B5. the pod / pod-owner endpoints that already exist")
hits(BE / "app" / "api" / "v1" / "admin.py", r"pod[-_](performance|owner)", context=3)
hits(BE / "app" / "services" / "admin_service.py", r"^async def |^def ", context=0)

rule("B6. the client hooks and the Filters shape")
hits(FE / "lib" / "api-hooks.ts", r"[Pp]od[OP]|pod-performance|pod-owner", context=1)
hits(FE / "lib" / "filters.ts", r"^export |pods|hou|publishers|owner")

print("\nread-only: nothing was written.")

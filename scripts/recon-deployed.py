#!/usr/bin/env python3
"""Print the deployed regions the remaining patch scripts must anchor to. Changes NOTHING.

WHY THIS EXISTS
---------------
Anchored patch scripts are only as good as my picture of the file they land on, and that
picture has been wrong five times - each wrong guess costing a full six-minute gate cycle.
This reads the real files once and prints just the regions that matter, so the next round
is anchored against fact instead of memory and can ship as ONE batch.

It writes nothing, touches no container, and exits 0 even when a region is missing (a
missing region is itself the answer: that feature is not deployed).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(".")

# (file, label, start-pattern, how many lines to show)
REGIONS: list[tuple[str, str, str, int]] = [
    # ── the app-category filter the owner asked for (appears NOT to be deployed) ──
    ("backend/app/schemas/metrics.py", "MetricFilters (the whole filter model)",
     r"^class MetricFilters", 70),
    ("backend/app/schemas/metrics.py", "the per-dimension input cap",
     r"dimensions = \(", 16),
    ("backend/app/api/v1/metrics.py", "the filter dependency - params in, model out",
     r"^def (?:filter_params|_filter_params|common_filters)|^async def (?:filter_params|_filter_params|common_filters)", 60),
    ("backend/app/services/query_builder.py", "where the narrowing filters are applied",
     r"if params\.apps:", 30),

    # ── super admin: the owner asked for it to be removed entirely ──
    ("backend/app/services/admin_service.py", "super-admin block, if still present",
     r"SUPER_ADMIN_ROLE = ", 45),
    ("backend/app/services/admin_service.py", "is_active_admin + the admin-count query",
     r"^def is_active_admin", 30),
    ("backend/app/api/v1/admin.py", "update_user: the guard region",
     r"guard_target_management|Last-active-admin lockout guard", 22),

    # ── App Master edits by any role, with approval ──
    ("backend/app/services/app_master_service.py", "who may propose / who may approve",
     r"^(async )?def (propose|submit|request_change|approve)", 30),
    ("backend/app/api/v1/app_master.py", "the route guards",
     r"^@router\.(post|patch|put)", 24),

    # ── the chatbot, scope-bound ──
    ("backend/app/services/chat_service.py", "tool dispatch + how scope reaches SQL",
     r"^async def _run_tool|^def _run_tool", 45),

    # ── my own hardening, still unshipped ──
    ("backend/app/services/query_builder.py", "previous_period arithmetic",
     r"length = \(params\.date_to - params\.date_from\)\.days", 12),
    ("backend/app/services/query_builder.py", "keyset ordering / cursor",
     r"sort_col = inner\.c\[sort\]", 14),
    ("backend/app/services/metrics_service.py", "encode_cursor",
     r"^def encode_cursor", 10),
    ("backend/app/api/v1/meta.py", "the freshness route",
     r'@router\.get\("/freshness"\)', 30),
]

IMPORT_HEADS = [
    "backend/app/services/query_builder.py",
    "backend/app/services/admin_service.py",
    "backend/app/services/access_service.py",
    "backend/app/api/v1/export.py",
    "backend/app/api/v1/meta.py",
]


def show(rel: str, label: str, pattern: str, count: int) -> None:
    path = ROOT / rel
    print(f"\n===== {rel} :: {label}")
    if not path.exists():
        print("  (file does not exist here)")
        return
    lines = path.read_text().splitlines()
    rx = re.compile(pattern)
    hits = [i for i, line in enumerate(lines) if rx.search(line)]
    if not hits:
        print("  (NOT PRESENT - nothing matches; that is the answer)")
        return
    for start in hits[:2]:
        print(f"  --- from line {start + 1}")
        for n in range(start, min(len(lines), start + count)):
            print(f"  {n + 1:>4}  {lines[n]}")


def main() -> int:
    print("RECON ONLY - nothing was written, nothing was restarted.")
    for rel, label, pattern, count in REGIONS:
        show(rel, label, pattern, count)

    print("\n\n########## import heads (so new imports land in the right isort group)")
    for rel in IMPORT_HEADS:
        path = ROOT / rel
        print(f"\n===== {rel}")
        if not path.exists():
            print("  (file does not exist here)")
            continue
        for n, line in enumerate(path.read_text().splitlines()[:34], 1):
            print(f"  {n:>4}  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

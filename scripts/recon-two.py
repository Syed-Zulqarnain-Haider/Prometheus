#!/usr/bin/env python3
"""Second and last recon: the three regions the category filter and the leftovers need.

The first pass answered most of it - super_admin is gone from admin_service, App Master
approval is live, the data-maturity date is live, and three of four data-path guards are
already in. What it could NOT answer, because my regexes were wrong about the names:

  1. the filter dependency in metrics.py is called get_filters, not filter_params
  2. where App Master proposals are gated (the service is not app_master_service)
  3. whether super_admin survives anywhere else (step_up, frontend, seeds)
  4. what the filter-options endpoint offers, so a category dropdown has values

Writes nothing. Restarts nothing. Exits 0 regardless.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(".")


def block(rel: str, label: str, pattern: str, count: int, limit: int = 2) -> None:
    path = ROOT / rel
    print(f"\n===== {rel} :: {label}")
    if not path.exists():
        print("  (file does not exist here)")
        return
    lines = path.read_text().splitlines()
    rx = re.compile(pattern)
    hits = [i for i, ln in enumerate(lines) if rx.search(ln)]
    if not hits:
        print("  (NOT PRESENT)")
        return
    for start in hits[:limit]:
        print(f"  --- from line {start + 1}")
        for n in range(start, min(len(lines), start + count)):
            print(f"  {n + 1:>4}  {lines[n]}")


def grep(label: str, pattern: str, *paths: str) -> None:
    print(f"\n===== grep :: {label}")
    try:
        out = subprocess.run(
            ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.tsx",
             "-E", pattern, *paths],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover - recon only
        print(f"  (grep failed: {exc})")
        return
    print("  (no hits)" if not out else "\n".join(f"  {ln}" for ln in out.splitlines()[:60]))


def main() -> int:
    print("RECON TWO - nothing was written, nothing was restarted.")

    # 1. the filter dependency every metrics route depends on
    block("backend/app/api/v1/metrics.py", "get_filters - the filter dependency",
          r"^(async )?def get_filters", 70)

    # 2. the filter-options endpoint, so a category dropdown can be populated
    block("backend/app/api/v1/meta.py", "_OPTION_DIMS in full", r"_OPTION_DIMS", 22)

    # 3. App Master proposals: who may propose, who may decide
    grep("app master request services", r"class .*(Request|Proposal)|def (propose|decide|approve|reject)",
         "backend/app/services", "backend/app/api/v1")

    # 4. does super_admin survive anywhere at all
    grep("any surviving super_admin", r"super_admin|SUPER_ADMIN|Super Admin|superadmin",
         "backend", "frontend")

    # 5. the frontend filter bar, so the category control lands beside the others
    grep("frontend filter dimensions", r"pod_owners|podOwners", "frontend/components/filters",
         "frontend/lib")

    # 6. the keyset sort block, whatever it is called now
    block("backend/app/services/query_builder.py", "the sort / cursor block",
          r"def table\(|order_by\(", 20, limit=3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Rides along with the batch: the last two regions, at no extra gate cost.

Recon two answered the filter and the super_admin leftovers. Still unknown, and both are
things the owner explicitly asked for:

  1. who may PROPOSE an App Master change (approval is live; the ask is that every
     assigned role can propose, not only admins)
  2. what the chat tests are given, so a scope-proof test uses the real fixtures instead
     of the ones I assumed - the last attempt seeded nothing and passed vacuously

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
    out = subprocess.run(
        ["grep", "-rn", "--include=*.py", "-E", pattern, *paths],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    print("  (no hits)" if not out else "\n".join(f"  {ln}" for ln in out.splitlines()[:40]))


def main() -> int:
    print("RECON THREE - nothing was written, nothing was restarted.")
    block("backend/app/services/app_master_request_service.py",
          "propose - who is allowed to, and what it checks", r"^async def propose", 40)
    block("backend/app/api/v1/app_master_requests.py",
          "the propose route and its guard", r"^@router\.post", 26, limit=2)
    grep("capability / role gates on App Master",
         r"require_capability|EDITABLE|_may_|is_admin|admin_panel",
         "backend/app/api/v1/app_master_requests.py",
         "backend/app/api/v1/app_master.py",
         "backend/app/services/app_master_request_service.py")
    grep("chat test fixtures", r"^(async )?def (chat_env|metrics_env|_seed)",
         "backend/tests/conftest.py")
    block("backend/tests/test_chat.py", "how an existing chat test is set up",
          r"^(async )?def test_claude_answers_using_scoped_totals", 26)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

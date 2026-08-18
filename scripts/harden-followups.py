#!/usr/bin/env python3
"""Two small follow-ups from the security re-audit.

1. backend/app/api/v1/meta.py - the /targets gate uses the same metric as pacing.
   The re-audit proved the two gates (total_revenue_usd here, rpt_gross_revenue_usd in
   pacing_service) evaluate IDENTICALLY today - both are plain additive columns in the
   same profitability group, and permissions are group-granular, so no role can hold
   one without the other. But that identity holds only as long as the registry keeps
   them grouped together; unifying the constants means a future regrouping cannot
   silently split the two gates and open a disclosure difference.

2. frontend/components/layout/notification-bell.tsx - reject backslashes in links.
   WHATWG URL parsing treats a backslash like a slash for http(s), so "/\\evil.com"
   passes the current startsWith checks yet resolves off-origin if it ever reaches a
   full-URL context. The server only writes in-app paths today, so this is
   defence-in-depth, same as the guard it tightens.

Both anchors are lines written by the previous hardening scripts (harden-backend-audit,
harden-frontend-inputs) - run those first; this aborts cleanly on an unhardened tree.

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
Backend restart + frontend rebuild; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

META = Path("backend/app/api/v1/meta.py")
BELL = Path("frontend/components/layout/notification-bell.tsx")

META_ANCHOR = '    if "total_revenue_usd" not in QueryBuilder(context).permitted_measures:\n'
META_NEW = (
    "    # Same metric as pacing_service._REVENUE, so the two gates can never drift apart\n"
    "    # if the registry ever regroups these columns.\n"
    '    if "rpt_gross_revenue_usd" not in QueryBuilder(context).permitted_measures:\n'
)

BELL_ANCHOR = '    if (n.link && n.link.startsWith("/") && !n.link.startsWith("//")) {\n'
BELL_NEW = (
    "    // No backslashes either: WHATWG URL parsing treats \\ like / for http(s), so\n"
    '    // "/\\\\evil.com" would resolve off-origin in a full-URL context.\n'
    '    if (\n'
    '      n.link &&\n'
    '      n.link.startsWith("/") &&\n'
    '      !n.link.startsWith("//") &&\n'
    '      !n.link.includes("\\\\")\n'
    "    ) {\n"
)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for path in (META, BELL):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    meta = META.read_text()
    bell = BELL.read_text()

    todo: dict[Path, str] = {}

    if "rpt_gross_revenue_usd" in meta:
        print(f"{META}: gates already unified")
    else:
        if meta.count(META_ANCHOR) != 1:
            die(f"{META}: hardened gate line not found - run harden-backend-audit.py first")
        todo[META] = meta.replace(META_ANCHOR, META_NEW, 1)

    if 'includes("\\\\")' in bell:
        print(f"{BELL}: backslashes already rejected")
    else:
        if bell.count(BELL_ANCHOR) != 1:
            die(f"{BELL}: hardened link guard not found - run harden-frontend-inputs.py first")
        todo[BELL] = bell.replace(BELL_ANCHOR, BELL_NEW, 1)

    if not todo:
        print("already hardened - nothing to do")
        return

    for path, text in todo.items():
        path.write_text(text)
        print(f"patched {path}")


if __name__ == "__main__":
    main()

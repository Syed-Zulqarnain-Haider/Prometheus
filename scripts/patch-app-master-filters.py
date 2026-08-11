#!/usr/bin/env python3
"""Add Pod owner / App name / Partner filters to the App Master page.

Run from the repository root:

    python3 scripts/patch-app-master-filters.py

Why a patch script and not edited files: these four files live only in the deployed tree,
so they are edited here by anchored replacement rather than overwritten from a copy that
might be older than yours. Every anchor must match EXACTLY ONCE or the script aborts having
written nothing - it will never half-apply.

It is safe to run twice: an already-patched file is detected and skipped.

What it changes:
  backend/app/schemas/app_master.py      + app_names on AppMasterFilterValues
  backend/app/services/app_master_service.py
                                         + pod_owner / app_name / partner_name filters
                                         + app_names in filter_values()
  backend/app/api/v1/app_master.py       + the three query params on GET /app-master
  frontend/lib/api-hooks.ts              + the three fields on AppMasterFilters,
                                           + app_names on AppMasterFilterValues
"""

from __future__ import annotations

import sys
from pathlib import Path

# (path, already-applied marker, [(anchor, replacement), ...])
PATCHES: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "backend/app/schemas/app_master.py",
        "app_names: list[str]",
        [
            (
                "    pod_owners: list[str]\n    partner_names: list[str]\n",
                "    pod_owners: list[str]\n"
                "    partner_names: list[str]\n"
                "    # Filter bar only: distinct app names, so App Master can offer an app-name\n"
                "    # dropdown instead of leaning on the free-text search.\n"
                "    app_names: list[str]\n",
            ),
        ],
    ),
    (
        "backend/app/services/app_master_service.py",
        "_TABLE.c.pod_owner.in_(",
        [
            # _apply_filters signature (no defaults - distinguishes it from list_rows).
            (
                "    pod: int | None,\n"
                "    needs_review: bool | None,\n"
                "    package: str | None,\n"
                "    app_id: str | None,\n",
                "    pod: int | None,\n"
                "    pod_owner: list[str],\n"
                "    app_name: list[str],\n"
                "    partner_name: list[str],\n"
                "    needs_review: bool | None,\n"
                "    package: str | None,\n"
                "    app_id: str | None,\n",
            ),
            # _apply_filters body: exact IN lists, matching platform/hou/publisher.
            (
                "    if pod is not None:\n        stmt = stmt.where(_TABLE.c.pod == pod)\n",
                "    if pod is not None:\n"
                "        stmt = stmt.where(_TABLE.c.pod == pod)\n"
                "    if pod_owner:\n"
                "        stmt = stmt.where(_TABLE.c.pod_owner.in_(pod_owner))\n"
                "    if app_name:\n"
                "        stmt = stmt.where(_TABLE.c.app_name.in_(app_name))\n"
                "    if partner_name:\n"
                "        stmt = stmt.where(_TABLE.c.partner_name.in_(partner_name))\n",
            ),
            # list_rows signature.
            (
                "    pod: int | None = None,\n    needs_review: bool | None = None,\n",
                "    pod: int | None = None,\n"
                "    pod_owner: list[str] | None = None,\n"
                "    app_name: list[str] | None = None,\n"
                "    partner_name: list[str] | None = None,\n"
                "    needs_review: bool | None = None,\n",
            ),
            # list_rows filter dict.
            (
                '        "pod": pod,\n        "needs_review": needs_review,\n',
                '        "pod": pod,\n'
                '        "pod_owner": pod_owner or [],\n'
                '        "app_name": app_name or [],\n'
                '        "partner_name": partner_name or [],\n'
                '        "needs_review": needs_review,\n',
            ),
            # filter_values: expose distinct app names too.
            (
                "        partner_names=[str(v) for v in await _distinct(_TABLE.c.partner_name)],\n"
                "    )\n",
                "        partner_names=[str(v) for v in await _distinct(_TABLE.c.partner_name)],\n"
                "        app_names=[str(v) for v in await _distinct(_TABLE.c.app_name)],\n"
                "    )\n",
            ),
        ],
    ),
    (
        "backend/app/api/v1/app_master.py",
        "pod_owner: Annotated[list[str], Query()]",
        [
            (
                "    pod: int | None = None,\n    needs_review: bool | None = None,\n",
                "    pod: int | None = None,\n"
                "    pod_owner: Annotated[list[str], Query()] = [],  # noqa: B006\n"
                "    app_name: Annotated[list[str], Query()] = [],  # noqa: B006\n"
                "    partner_name: Annotated[list[str], Query()] = [],  # noqa: B006\n"
                "    needs_review: bool | None = None,\n",
            ),
            (
                "        pod=pod,\n        needs_review=needs_review,\n",
                "        pod=pod,\n"
                "        pod_owner=pod_owner,\n"
                "        app_name=app_name,\n"
                "        partner_name=partner_name,\n"
                "        needs_review=needs_review,\n",
            ),
        ],
    ),
    (
        "frontend/lib/api-hooks.ts",
        "params.pod_owner = filters.podOwner",
        [
            (
                "  pod: string; // raw input; sent as int when numeric\n"
                '  needsReview: "" | "true" | "false";\n',
                "  pod: string; // raw input; sent as int when numeric\n"
                '  podOwner: string; // "" = all\n'
                '  appName: string; // "" = all\n'
                '  partnerName: string; // "" = all\n'
                '  needsReview: "" | "true" | "false";\n',
            ),
            (
                "  if (filters.needsReview) params.needs_review = filters.needsReview;\n",
                "  if (filters.podOwner) params.pod_owner = filters.podOwner;\n"
                "  if (filters.appName) params.app_name = filters.appName;\n"
                "  if (filters.partnerName) params.partner_name = filters.partnerName;\n"
                "  if (filters.needsReview) params.needs_review = filters.needsReview;\n",
            ),
            (
                "  pod_owners: string[];\n  partner_names: string[];\n}\n",
                "  pod_owners: string[];\n  partner_names: string[];\n  app_names: string[];\n}\n",
            ),
        ],
    ),
]


def main() -> int:
    root = Path.cwd()
    if not (root / "backend").is_dir() or not (root / "frontend").is_dir():
        print("ERROR: run this from the repository root (the folder holding backend/ and")
        print("       frontend/), e.g. cd ~/final_project/main_final_project/Prometheus")
        return 2

    planned: list[tuple[Path, str]] = []
    skipped: list[str] = []

    # Pass 1: verify everything before writing anything. A half-applied change across four
    # files is far worse than a clean abort.
    for rel, marker, edits in PATCHES:
        path = root / rel
        if not path.is_file():
            print(f"ERROR: {rel} not found.")
            return 2
        text = path.read_text(encoding="utf-8")
        if marker in text:
            skipped.append(rel)
            continue
        for anchor, replacement in edits:
            count = text.count(anchor)
            if count != 1:
                print(f"ERROR: {rel}: expected exactly 1 match, found {count}, for:")
                print("-" * 60)
                print(anchor.rstrip("\n"))
                print("-" * 60)
                print("Nothing was written. The file has probably changed since this patch")
                print("was written - send me the file and I'll rebuild the patch.")
                return 1
            text = text.replace(anchor, replacement)
        planned.append((path, text))

    for path, text in planned:
        path.write_text(text, encoding="utf-8")
        print(f"patched  {path.relative_to(root)}")
    for rel in skipped:
        print(f"skipped  {rel} (already patched)")

    if not planned:
        print("\nNothing to do - every file was already patched.")
    else:
        print("\nDone. Next:")
        print("  docker compose -f docker-compose.prod.yml up -d --build")
    return 0


if __name__ == "__main__":
    sys.exit(main())

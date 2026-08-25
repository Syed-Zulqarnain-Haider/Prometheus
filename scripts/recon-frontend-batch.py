#!/usr/bin/env python3
"""Read-only. Gathers the frontend facts the next batch of work depends on.

Writes nothing, changes nothing. Exists because the copy of this repo I work
from is behind the server, and every frontend patch I write blind is a patch
anchored to a file that may no longer look like that.

Covers, in order:
  1. nav + routes      - which pages exist, which are gated, which are orphaned
  2. bare -1 pods      - every place a pod renders WITHOUT the Unassigned label
  3. YTD / MTD         - the averages that should read as plain numbers
  4. Spotlight         - what it renders, and where it sends you to edit
  5. App Master editor - the drawer Spotlight should be able to open in place
  6. Chat panel        - what the assistant surface is today
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def show(path: Path, limit: int | None = None) -> None:
    if not path.exists():
        print(f"  (missing: {path.relative_to(ROOT)})")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    shown = lines if limit is None else lines[:limit]
    print(f"\n--- {path.relative_to(ROOT)} ({len(lines)} lines)")
    for number, line in enumerate(shown, 1):
        print(f"{number:5}: {line}")
    if limit is not None and len(lines) > limit:
        print(f"      ... {len(lines) - limit} more lines")


def grep(pattern: str, *, globs: tuple[str, ...] = ("**/*.ts", "**/*.tsx"),
         context: int = 0, skip: tuple[str, ...] = ("node_modules", ".next")) -> None:
    regex = re.compile(pattern)
    for glob in globs:
        for path in sorted(FRONTEND.glob(glob)):
            if any(part in skip for part in path.parts):
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if not regex.search(line):
                    continue
                low = max(0, index - context)
                high = min(len(lines), index + context + 1)
                print(f"\n{path.relative_to(ROOT)}:{index + 1}")
                for number in range(low, high):
                    mark = ">" if number == index else " "
                    print(f"  {mark} {number + 1:4}: {lines[number]}")


# 1 ── nav + routes ----------------------------------------------------------
rule("1. nav definition")
show(FRONTEND / "lib" / "nav.ts")

rule("1b. every route that exists under app/")
pages = sorted(FRONTEND.glob("app/**/page.tsx"))
routes = []
for page in pages:
    route = "/" + str(page.parent.relative_to(FRONTEND / "app")).replace("\\", "/")
    route = "/" if route == "/." else route
    routes.append(route)
    body = page.read_text(encoding="utf-8")
    kind = "redirect" if "redirect(" in body else f"{len(body.splitlines())} lines"
    print(f"  {route:32} {kind}")

rule("1c. routes with no nav entry (candidates to redirect or to surface)")
nav = (FRONTEND / "lib" / "nav.ts")
nav_text = nav.read_text(encoding="utf-8") if nav.exists() else ""
for route in routes:
    if route not in nav_text and route != "/":
        print(f"  {route}")

# 2 ── bare -1 pods ----------------------------------------------------------
rule("2. every place a pod value is rendered")
grep(r"\bpod\b(?!_)", globs=("components/**/*.tsx", "app/**/*.tsx"), context=1)

rule("2b. who already uses the Unassigned helper")
grep(r"podLabel|isUnassignedPod|UNASSIGNED")

# 3 ── YTD / MTD averages ----------------------------------------------------
rule("3. YTD / MTD and the averages shown inside them")
grep(r"YTD|MTD|ytd|mtd|[Aa]verage|avg", context=2)

# 4 ── Spotlight -------------------------------------------------------------
rule("4. Spotlight: what it renders and where it links out to")
for name in ("spotlight", "apps-admin"):
    for path in sorted(FRONTEND.glob(f"**/*{name}*")):
        if any(part in path.parts for part in ("node_modules", ".next")) or path.is_dir():
            continue
        show(path, limit=160)

# 5 ── App Master editor -----------------------------------------------------
rule("5. the App Master edit surface Spotlight should reuse")
grep(r"app-master|appMaster|AppMaster", globs=("components/**/*.tsx", "lib/**/*.ts"))

# 6 ── chat ------------------------------------------------------------------
rule("6. the chat / assistant surface today")
for path in sorted(FRONTEND.glob("**/*chat*")):
    if any(part in path.parts for part in ("node_modules", ".next")) or path.is_dir():
        continue
    show(path, limit=120)

print("\nread-only: nothing was written.")

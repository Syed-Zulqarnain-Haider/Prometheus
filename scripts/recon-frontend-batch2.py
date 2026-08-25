#!/usr/bin/env python3
"""Read-only, compact. The exact regions the next patches need, and nothing else.

Replaces recon-frontend-batch.py, which had two faults: it compared routes
WITHOUT stripping Next's (group) segments - so every route looked orphaned,
which is a wrong answer, not a partial one - and it dumped every mention of
"pod" rather than the places a pod is actually rendered.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
SKIP = ("node_modules", ".next", "dist")
GROUP = re.compile(r"/\([^)]*\)")


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def sources() -> list[Path]:
    found: list[Path] = []
    for pattern in ("**/*.ts", "**/*.tsx"):
        for path in FRONTEND.glob(pattern):
            if not any(part in SKIP for part in path.parts):
                found.append(path)
    return sorted(set(found))


def dump(path: Path, first: int = 1, last: int | None = None, cap: int = 220) -> None:
    if not path.exists():
        print(f"  (missing: {path})")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    last = min(last or len(lines), len(lines))
    if last - first + 1 > cap:
        last = first + cap - 1
    print(f"\n--- {path.relative_to(ROOT)}  [lines {first}-{last} of {len(lines)}]")
    for number in range(first, last + 1):
        print(f"{number:5}: {lines[number - 1]}")


def region(path: Path, pattern: str, before: int = 4, after: int = 22) -> None:
    """The block around the first line matching `pattern`."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if re.search(pattern, line):
            dump(path, max(1, index - before + 1), index + after + 1)
            return
    print(f"  ({pattern!r} not found in {path.relative_to(ROOT)})")


# 1 ── sidebar grouping ------------------------------------------------------
rule("1. the sidebar - where MORE comes from")
for path in sources():
    text = path.read_text(encoding="utf-8")
    if "visibleNavItems" in text or "NAV_ITEMS" in text:
        if path.name == "nav.ts":
            continue
        dump(path, cap=200)

rule("1b. anything that groups nav items")
for path in sources():
    text = path.read_text(encoding="utf-8")
    if re.search(r'"MORE"|\bMORE\b|group.*[Nn]av|[Nn]av.*group|SECTION', text):
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(r'MORE|SECTION|group', line):
                print(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")

# 2 ── routes vs nav, with route groups stripped -----------------------------
rule("2. routes vs nav (Next route groups stripped this time)")
nav_text = (FRONTEND / "lib" / "nav.ts").read_text(encoding="utf-8")
in_nav = set(re.findall(r'href:\s*"([^"]+)"', nav_text))
print(f"  nav declares {len(in_nav)} routes")
for page in sorted(FRONTEND.glob("app/**/page.tsx")):
    raw = "/" + str(page.parent.relative_to(FRONTEND / "app")).replace("\\", "/")
    route = GROUP.sub("", raw) or "/"
    body = page.read_text(encoding="utf-8")
    dynamic = "[" in route
    state = (
        "REDIRECT" if "redirect(" in body
        else "in nav" if route in in_nav
        else "dynamic (no nav entry expected)" if dynamic
        else "ORPHAN - reachable, not in the sidebar"
    )
    print(f"  {route:32} {state}")

rule("2b. the thin pages, in full (5-line files - what do they render?)")
for name in ("spotlight", "app-master", "app-changes", "pod-owners", "security", "apps-admin"):
    for page in FRONTEND.glob(f"app/**/{name}/page.tsx"):
        dump(page, cap=40)

# 3 ── pod rendering without the Unassigned label ----------------------------
rule("3. pod RENDERED without podLabel() - the remaining bare -1s")
render = re.compile(
    r"(value=\{[^}]*\bpod\b[^}]*\}|\{[^}]*\brow\.pod\b[^}]*\}|\{[^}]*\.pod\b[^}]*\}"
    r"|String\([^)]*\bpod\b[^)]*\)|key:\s*\"pod\"|groupBy=\"pod\")"
)
for path in sources():
    text = path.read_text(encoding="utf-8")
    if "pod" not in text:
        continue
    uses_helper = "podLabel" in text or "isUnassignedPod" in text
    lines = text.splitlines()
    hits = [(n, line) for n, line in enumerate(lines, 1) if render.search(line)]
    if not hits:
        continue
    print(f"\n{path.relative_to(ROOT)}   helper: {'YES' if uses_helper else 'NO'}")
    for number, line in hits:
        print(f"   {number:5}: {line.strip()}")

# 4 ── App Master edit surface ----------------------------------------------
rule("4. App Master client - the pod>0 guard, the pod input, the column config")
client = FRONTEND / "components" / "app-master" / "app-master-client.tsx"
region(client, r"Client-side guards matching the backend", before=6, after=34)
region(client, r'c\.name === "pod"', before=8, after=24)
region(client, r"const OPTIONS", before=4, after=26)

rule("4b. its props and exported shape (so Spotlight can mount the same editor)")
if client.exists():
    lines = client.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        if re.search(r"^export |^interface |^type |^function |^const \w+ = \(|useMutation|useEditRow|apiFetch", line):
            print(f"{number:5}: {line}")

# 5 ── YTD / MTD averages ----------------------------------------------------
rule("5. YTD / MTD blocks")
for path in sources():
    text = path.read_text(encoding="utf-8")
    if re.search(r"\bYTD\b|\bMTD\b", text):
        dump(path, cap=200)

# 6 ── Spotlight -------------------------------------------------------------
rule("6. Spotlight component")
for path in sources():
    if "spotlight" in path.name.lower():
        dump(path, cap=200)

# 7 ── chat ------------------------------------------------------------------
rule("7. chat surface")
for path in sources():
    if "chat" in path.name.lower() and path.suffix == ".tsx":
        dump(path, cap=160)

print("\nread-only: nothing was written.")

#!/usr/bin/env python3
"""Read-only evidence for spec Section 6 (S1-S6) and the 'Keep' regressions.

The browser audit could not reach any of this. None of it is an exploit - every
check reads source and reports what is actually there, so the tickets that say
'confirm' get confirmed instead of assumed.

  S1  every raw-HTML sink, with context, and whether user data can reach it
  S3  do reports / saved views / chat / users use guessable ids?
  S4  any SQL built by string interpolation rather than parameters
  S5  logout: is the token actually cleared, and is the cache invalidated?
  S6  are the expensive operations admin-gated AND single-flight, server-side?
  KEEP  request_id on errors, header auth with no cookie, no leaked internals

Writes nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
BE = ROOT / "backend"
SKIP = ("node_modules", ".next", "__pycache__", "dist")


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def sources(root: Path, *patterns: str) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            if not any(part in SKIP for part in path.parts):
                found.append(path)
    return sorted(set(found))


def scan(paths: list[Path], pattern: str, context: int = 0, limit: int = 200) -> int:
    regex = re.compile(pattern)
    total = 0
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for index, line in enumerate(lines):
            if not regex.search(line) or total >= limit:
                continue
            total += 1
            print(f"\n{path.relative_to(ROOT)}:{index + 1}")
            for number in range(max(0, index - context), min(len(lines), index + context + 1)):
                mark = ">" if number == index else " "
                print(f"  {mark} {number + 1:5}: {lines[number].rstrip()[:150]}")
    if total == 0:
        print("  (no matches)")
    return total


TSX = sources(FE, "*.ts", "*.tsx")
PY = sources(BE / "app", "*.py")

# ── S1 ───────────────────────────────────────────────────────────────────────
rule("S1. raw-HTML sinks (spec calls this the highest priority)")
print("-- dangerouslySetInnerHTML / innerHTML, with surrounding context --")
sinks = scan(TSX, r"dangerouslySetInnerHTML|\.innerHTML\s*=|insertAdjacentHTML", context=6)
print(f"\n  TOTAL SINKS: {sinks}   (the audit reported 14 + 4 in the built bundle;")
print("   a sink in a third-party dependency is not one of ours - these are ours)")

print("\n-- is a sanitizer present at all? --")
scan(sources(FE, "package.json"), r"dompurify|sanitize-html|xss")

print("\n-- fields that carry user-supplied text, for the render audit --")
scan(TSX, r"display_name|displayName|job_title|jobTitle|\bbody\b.*message|announcement|report_name|view_name|scope_value", limit=40)

# ── S3 ───────────────────────────────────────────────────────────────────────
rule("S3. object ids - guessable or not")
scan(PY, r"^\s*id\s*[:=].*(UUID|uuid|Integer|BigInteger)|primary_key=True", limit=60)

# ── S4 ───────────────────────────────────────────────────────────────────────
rule("S4. SQL built by interpolation rather than parameters")
print("-- f-string / concat inside text() or execute() - CLAUDE.md permits ONLY the")
print("   sync job's DDL, whose identifiers come from the registry, never from a user --")
scan(PY, r'(text|execute)\(\s*f["\']|["\']\s*\+\s*\w+\s*\+\s*["\'].*(SELECT|WHERE|FROM)', context=2)
print("\n-- allowlists that must gate any dimension reaching SQL --")
scan(PY, r"_GROUP_BY_COLUMN|sort_whitelist|Literal\[|permitted_measures", limit=40)

# ── S5 ───────────────────────────────────────────────────────────────────────
rule("S5. session lifecycle - what logout actually does")
scan(TSX, r"signOut|logout|clearToken|removeItem|queryClient\.(clear|removeQueries|invalidateQueries)", context=3, limit=40)

# ── S6 ───────────────────────────────────────────────────────────────────────
rule("S6. expensive operations - admin gate and single-flight, server-side")
for name in ("sync", "backfill", "clear", "digest", "evaluate", "alert"):
    print(f"\n---- /{name} ----")
    scan(sources(BE / "app" / "api", "*.py"), rf'@router\.(post|put|delete)\("[^"]*{name}[^"]*"', context=6, limit=12)
print("\n-- single-flight: is there a lock, and is it the SAME key everywhere? --")
scan(PY, r"advisory_lock|ADVISORY_LOCK|single.?flight|NX=True|nx=True", context=2)
print("\n-- capability gates on the admin router --")
scan(sources(BE / "app" / "api", "*.py"), r"require_capability|require_role|Depends\(require", limit=40)

# ── KEEP ─────────────────────────────────────────────────────────────────────
rule("KEEP. the things the audit called good - do they still hold?")
print("-- request_id on structured errors --")
scan(PY, r"request_id", limit=20)
print("\n-- header auth, no ambient cookie --")
scan(TSX, r"Authorization|Bearer|credentials:\s*[\"']include[\"']|document\.cookie", limit=25)
print("\n-- rate limiting (P1-21 says none exists; confirm) --")
scan(PY, r"rate.?limit|RateLimit|429|Retry-After", limit=30)

# ── P1-15 / P1-22 inventory ──────────────────────────────────────────────────
rule("P1-15. every <Link> and whether it prefetches")
total = with_prefetch = 0
for path in TSX:
    text = path.read_text(encoding="utf-8")
    links = len(re.findall(r"<Link\b", text))
    pref = len(re.findall(r"<Link\b[^>]*prefetch", text, re.S))
    if links:
        total += links
        with_prefetch += pref
        print(f"  {str(path.relative_to(ROOT)):64} {links:3} link(s), {pref} with prefetch")
print(f"\n  TOTAL: {total} links, {with_prefetch} declare prefetch, {total - with_prefetch} default (= prefetch ON)")

rule("P1-22. heading levels actually rendered")
scan(TSX, r"<h[1-6]\b|CardTitle|PageHeader|role=\"heading\"|skip.?to.?content", limit=60)

print("\nread-only: nothing was written.")

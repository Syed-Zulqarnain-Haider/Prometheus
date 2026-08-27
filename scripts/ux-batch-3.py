#!/usr/bin/env python3
"""UX batch 3: an App Master edit updates the numbers on screen, not on the next refresh.

This is the other half of a bug I only half-fixed. Changing an app's pod or HoU busts the
SERVER's aggregate cache - that shipped. But the browser keeps its own cache, and the
aggregate queries carry a 60-second staleTime, while the App Master mutations only ever
invalidated ``["app-master"]``. So the table you just edited updated instantly and every
number derived from it - Overview, Revenue, Pod Owner, the drill-throughs - kept showing
the old attribution until you reloaded the page. Exactly "it only updates when I refresh".

The fix is deliberately blunt: after an attribution edit, drop the WHOLE query cache. A
pod change can move any number on any page, so an allowlist of "keys that might be
affected" would be a list that silently goes stale every time a page is added. Only
queries that are actually mounted refetch immediately; everything else is simply marked
stale and refetches when you next look at it, so the cost is one refetch of the page you
are already on.

Call sites are FOUND, not assumed: any `invalidateQueries({ queryKey: ["app-master"] })`
anywhere under frontend/ is rewired, whatever the surrounding hook is called and whatever
the query-client variable is named. If there are none, the run says so instead of
silently doing nothing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
HELPER_TS = ROOT / "frontend/lib/invalidate.ts"

HELPER_SOURCE = """"use client";

import type { QueryClient } from "@tanstack/react-query";

/**
 * Forget every cached answer after an App Master edit.
 *
 * Attribution is not a local fact. Moving one app between pods changes that pod's
 * revenue, the other pod's revenue, the HoU rollup above both, the pod-owner table, the
 * Overview donuts, every breakdown grouped by pod, and the drill-through pages behind
 * them - and because live attribution rewrites HISTORY rather than only today, it moves
 * numbers for every date range at once, not just the current one.
 *
 * So there is no honest short list of "the queries this affects". Enumerating keys here
 * would produce a list that is correct on the day it is written and quietly wrong the
 * first time somebody adds a page - and the failure mode is the worst kind: a dashboard
 * that shows a stale number with total confidence.
 *
 * Invalidation is cheap. React Query refetches only what is currently mounted and marks
 * the rest stale, so this costs one refetch of the screen you are already looking at.
 * The server-side aggregate cache is busted by the same edit, so what comes back is the
 * new attribution rather than a cached copy of the old one.
 */
export function invalidateAfterAttributionChange(client: QueryClient): void {
  void client.invalidateQueries();
}
"""

# Any `<something>.invalidateQueries({ queryKey: ["app-master", ...] })`, however the
# query client is named locally and whatever else is in the key tuple.
CALL_RE = re.compile(
    r"(?P<client>[A-Za-z_][A-Za-z0-9_]*)\.invalidateQueries\(\s*\{\s*queryKey:\s*"
    r'\[\s*"app-master"[^\]]*\]\s*,?\s*\}\s*\)'
)
IMPORT_LINE = 'import { invalidateAfterAttributionChange } from "@/lib/invalidate";'

ENCLOSING_RE = re.compile(r"^(?:export )?function ([A-Za-z_][A-Za-z0-9_]*)", re.M)
# Not every App Master mutation changes attribution. Dragging a COLUMN around is a
# display preference; blowing away the cache for it would refetch the whole screen to
# move a header two places left.
NOT_ATTRIBUTION = re.compile(r"ColumnOrder|ColumnWidth", re.I)


def enclosing_function(text: str, position: int) -> str:
    """Name of the function a match sits inside - the last one declared above it."""
    names = [m.group(1) for m in ENCLOSING_RE.finditer(text, 0, position)]
    return names[-1] if names else ""


def add_import(text: str) -> str:
    if IMPORT_LINE in text:
        return text
    imports = list(re.finditer(r"^import [^\n]*;$", text, re.M))
    if not imports:
        return IMPORT_LINE + "\n" + text
    end = imports[-1].end()
    return text[:end] + "\n" + IMPORT_LINE + text[end:]


def candidates() -> list[Path]:
    found: list[Path] = []
    for pattern in (
        "frontend/lib/**/*.ts",
        "frontend/lib/**/*.tsx",
        "frontend/components/**/*.tsx",
    ):
        for path in ROOT.glob(pattern):
            if "node_modules" in path.parts:
                continue
            found.append(path)
    return sorted(set(found))


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    writes: dict[Path, str] = {}
    done: list[str] = []

    if not HELPER_TS.exists() or HELPER_TS.read_text() != HELPER_SOURCE:
        writes[HELPER_TS] = HELPER_SOURCE
        done.append(f"{HELPER_TS} written")

    rewired = 0
    for path in candidates():
        text = path.read_text()
        if "invalidateQueries" not in text:
            continue
        matches = [
            m
            for m in CALL_RE.finditer(text)
            if not NOT_ATTRIBUTION.search(enclosing_function(text, m.start()))
        ]
        if not matches:
            continue
        # Applied back to front so each replacement cannot shift the next one's offsets.
        patched = text
        for match in reversed(matches):
            patched = (
                patched[: match.start()]
                + f"invalidateAfterAttributionChange({match.group('client')})"
                + patched[match.end() :]
            )
        patched = add_import(patched)
        writes[path] = patched
        rewired += len(matches)
        hooks = ", ".join(
            sorted({enclosing_function(text, m.start()) for m in matches})
        )
        done.append(f"{path}: {len(matches)} call site(s) rewired ({hooks})")

    if rewired == 0:
        already = sum(
            1
            for path in candidates()
            if path != HELPER_TS
            and "invalidateAfterAttributionChange(" in path.read_text()
        )
        if already:
            print(
                f"Nothing to do - {already} file(s) already call "
                "invalidateAfterAttributionChange()."
            )
            for path, text in writes.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return 0
        print(
            "ABORTED - nothing was written.\n\n"
            "[app-master-invalidation] found no `invalidateQueries({ queryKey: "
            '["app-master"] })` anywhere under frontend/. Either the App Master '
            "mutations invalidate under a different key now, or they no longer\n"
            "invalidate at all. Files that mutate App Master:",
            file=sys.stderr,
        )
        for path in candidates():
            text = path.read_text()
            if "app-master" in text and "useMutation" in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if "invalidateQueries" in line or "app-master" in line:
                        print(f"  {path}:{i}  {line.strip()}", file=sys.stderr)
        return 1

    for path, text in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    print(
        "PATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    for line in done:
        print(f"  - {line}")
    print(
        f"  - an App Master edit now drops the whole client cache "
        f"({rewired} call site(s)), so every derived number re-reads the new attribution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

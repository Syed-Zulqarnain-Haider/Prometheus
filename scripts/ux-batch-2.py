#!/usr/bin/env python3
"""UX batch 2: tabs that survive a refresh, Unassigned in Apps Explorer, and the
server-side half of the sidebar order - plus the recon the last four items need.

Sections are INDEPENDENT here (unlike batch 1): each one stages its own writes and a
section that cannot match its anchors is skipped and reported, without taking the others
down with it. They touch disjoint files, and every section is idempotent, so re-running
after a fix is safe.

  A. NAV ORDER, SERVER SIDE.  `dashboard_layouts` gains a second allowed page, "nav", so
     a user's sidebar order can live on their account instead of in one browser's
     localStorage. Same per-user table, same audit action, no migration - the row is
     keyed (user_id, page) and the payload is free-form JSON.

  B. useNavOrder().  The client half of the same thing: reads the saved order, migrates
     whatever is already in localStorage up to the server the first time, and keeps a
     local mirror so the sidebar still paints instantly on reload. NOT yet wired into
     sidebar.tsx - that file has diverged from this tree and gets one anchored line once
     section E has printed it.

  C. APPS EXPLORER.  The Pod column still renders a raw "-1". Routed through the shared
     dimensionLabel() so it reads "Unassigned" here exactly as it does everywhere else -
     one rule, not a second copy of it.

  D. TABS SURVIVE A REFRESH.  Every `const [tab, setTab] = useState<Tab>(...)` becomes a
     URL-backed tab, so reloading Admin / Reports / Chat / Apps puts you back on the
     section you were on. The permitted values are read out of the file's own `type Tab`
     union rather than hardcoded here, so a page that grows a tab keeps working.

  E. RECON for the last four items: the sidebar's order code, the glossary page, the
     Spotlight board and the App Master edit drawer.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
LAYOUTS_API = ROOT / "backend/app/api/v1/layouts.py"
NAV_ORDER_TS = ROOT / "frontend/lib/nav-order.ts"
URL_TAB_TS = ROOT / "frontend/lib/use-url-tab.ts"
ATTRIBUTION_TS = ROOT / "frontend/lib/attribution.ts"
EXPLORER = ROOT / "frontend/components/apps/apps-explorer.tsx"
SIDEBAR = ROOT / "frontend/components/layout/sidebar.tsx"

skipped: list[str] = []
notes: list[str] = []


class Section:
    """One independent unit of work. Its writes land only if it finishes cleanly."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.writes: dict[Path, str] = {}
        self.reasons: list[str] = []
        self.done: list[str] = []

    def skip(self, reason: str, region: str = "") -> None:
        self.reasons.append(reason + (f"\n{indent(region)}" if region else ""))

    def commit(self) -> None:
        if self.reasons:
            skipped.append(
                f"[{self.name}] SKIPPED - nothing from this section was written:\n"
                + "\n".join(f"  * {r}" for r in self.reasons)
            )
            return
        for path, text in self.writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for line in self.done or ["already applied - left alone"]:
            notes.append(f"[{self.name}] {line}")


def indent(text: str) -> str:
    return "\n".join(f"      | {line}" for line in text.rstrip("\n").splitlines())


def window(text: str, needle: str, before: int = 3, after: int = 10) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(lines[max(0, i - before) : i + after])
    return "(not found anywhere in the file)"


def add_import(text: str, statement: str) -> str:
    """Append an import after the last existing one. Idempotent."""
    if statement in text:
        return text
    imports = list(re.finditer(r"^import [^\n]*;$", text, re.M))
    if not imports:
        return statement + "\n" + text
    end = imports[-1].end()
    return text[:end] + "\n" + statement + text[end:]


# ─────────────────────────────────────────────────────────────────────────────
# A. Allow a "nav" layout page
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_RE = re.compile(r"ALLOWED_PAGES\s*=\s*frozenset\(\{([^}]*)\}\)")


def section_allowed_pages() -> Section:
    section = Section("nav-allowed-page")
    if not LAYOUTS_API.exists():
        section.skip(f"missing {LAYOUTS_API}")
        return section
    text = LAYOUTS_API.read_text()

    match = ALLOWED_RE.search(text)
    if match is None:
        section.skip(
            "ALLOWED_PAGES is not the frozenset this patch expects",
            window(text, "ALLOWED_PAGES"),
        )
        return section
    pages = re.findall(r'"([^"]+)"', match.group(1))
    if "overview" not in pages:
        section.skip(
            f'ALLOWED_PAGES does not contain "overview" (found {pages})', match.group(0)
        )
        return section
    if "nav" in pages:
        return section

    replacement = (
        "ALLOWED_PAGES = frozenset({"
        + ", ".join(f'"{p}"' for p in [*pages, "nav"])
        + "})"
    )
    text = text[: match.start()] + replacement + text[match.end() :]
    section.writes[LAYOUTS_API] = text
    section.done.append(f'"nav" added -> {sorted([*pages, "nav"])}')
    return section


# ─────────────────────────────────────────────────────────────────────────────
# B. useNavOrder - the sidebar order on the account, not in one browser
# ─────────────────────────────────────────────────────────────────────────────

NAV_ORDER_SOURCE = """"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";

/* The sidebar's page order, stored against the USER rather than the browser.
 *
 * It used to live in localStorage, which meant a carefully arranged sidebar existed on
 * exactly one machine, in exactly one browser, until the day that profile was cleared.
 * It now rides on the same per-user dashboard_layouts row the Overview grid uses: same
 * table, same ownership rule (every query is scoped to the caller), same audit trail,
 * no new schema.
 *
 * localStorage is still written, but demoted to a cache: it is what paints the sidebar
 * on the very first frame after a reload, before the server has answered. The server is
 * the truth; the mirror only decides what you look at for ~100ms.
 */

const PAGE = "nav";
const CACHE_KEY = "nav-order";

interface NavLayout {
  order?: string[];
}

interface LayoutOut {
  page: string;
  layout: NavLayout | null;
  updated_at: string | null;
}

function cacheKey(userId: string | null | undefined): string {
  return userId ? `${CACHE_KEY}:${userId}` : CACHE_KEY;
}

function readCache(userId: string | null | undefined): string[] {
  try {
    const raw = window.localStorage.getItem(cacheKey(userId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((h): h is string => typeof h === "string") : [];
  } catch {
    return []; // storage blocked, or somebody hand-edited the value into nonsense
  }
}

function writeCache(userId: string | null | undefined, order: string[]): void {
  try {
    window.localStorage.setItem(cacheKey(userId), JSON.stringify(order));
  } catch {
    /* a cache that cannot be written is not an error - the server still has it */
  }
}

export interface NavOrder {
  /** Saved href order. Empty means "no preference" - render the default. */
  order: string[];
  /** Persist a new order for this user. Applies locally at once, then saves. */
  setOrder: (next: string[]) => void;
  /** False until the server has answered, so callers can avoid a visible re-sort. */
  ready: boolean;
}

export function useNavOrder(userId: string | null | undefined): NavOrder {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [order, setLocal] = useState<string[]>([]);
  const migrated = useRef(false);

  const query = useQuery({
    queryKey: ["dashboard-layout", PAGE],
    queryFn: () => apiFetch<LayoutOut>(`/api/v1/dashboard-layouts/${PAGE}`),
    enabled: Boolean(user),
    staleTime: 5 * 60 * 1000,
  });

  const save = useMutation({
    mutationFn: (next: string[]) =>
      apiFetch<LayoutOut>(`/api/v1/dashboard-layouts/${PAGE}`, {
        method: "PUT",
        body: JSON.stringify({ layout: { order: next } }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard-layout", PAGE] });
    },
  });

  // First paint: whatever this browser last saw. Corrected the moment the server answers.
  useEffect(() => {
    setLocal(readCache(userId));
  }, [userId]);

  useEffect(() => {
    if (!query.isSuccess) return;
    const saved = query.data.layout?.order;
    if (Array.isArray(saved) && saved.length > 0) {
      setLocal(saved);
      writeCache(userId, saved);
      return;
    }
    // Nothing on the account yet. If this browser has an order from before the move,
    // lift it up ONCE rather than throwing away an arrangement somebody made by hand.
    if (migrated.current) return;
    migrated.current = true;
    const legacy = readCache(userId);
    if (legacy.length > 0) save.mutate(legacy);
    // `save` is a stable mutation object; listing it would re-run this on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.isSuccess, query.data, userId]);

  const setOrder = useCallback(
    (next: string[]) => {
      setLocal(next);
      writeCache(userId, next);
      save.mutate(next);
    },
    // `save` is a stable mutation object from TanStack; listing it would rebuild this
    // callback on every render for no benefit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [userId],
  );

  return { order, setOrder, ready: query.isSuccess };
}
"""


def section_nav_order_hook() -> Section:
    section = Section("nav-order-hook")
    if NAV_ORDER_TS.exists() and NAV_ORDER_TS.read_text() == NAV_ORDER_SOURCE:
        return section
    section.writes[NAV_ORDER_TS] = NAV_ORDER_SOURCE
    section.done.append(f"{NAV_ORDER_TS} written (not yet wired into the sidebar)")
    return section


# ─────────────────────────────────────────────────────────────────────────────
# C. Apps Explorer: -1 is Unassigned, like everywhere else
# ─────────────────────────────────────────────────────────────────────────────

RAW_CELL = 'return String(value ?? "-");'
LABELLED_CELL = (
    '// Dimensions carry -1 for "nobody owns this yet". One shared rule turns that\n'
    '      // into "Unassigned" so this table cannot disagree with the charts.\n'
    "      return dimensionLabel(c.key, value);"
)


def section_explorer_unassigned() -> Section:
    section = Section("explorer-unassigned")
    if not EXPLORER.exists():
        section.skip(f"missing {EXPLORER}")
        return section
    if not ATTRIBUTION_TS.exists():
        section.skip(
            f"missing {ATTRIBUTION_TS} - refusing to import a module that is not there"
        )
        return section

    text = EXPLORER.read_text()
    if "dimensionLabel(" in text:
        return section

    hits = text.count(RAW_CELL)
    if hits != 1:
        section.skip(
            f"expected exactly one `{RAW_CELL}` in the cell renderer, found {hits}",
            window(text, "cell: ({ getValue"),
        )
        return section
    if "c.key" not in text:
        section.skip("the column object is not named `c` here", window(text, RAW_CELL))
        return section

    text = text.replace(RAW_CELL, LABELLED_CELL, 1)
    text = add_import(text, 'import { dimensionLabel } from "@/lib/attribution";')
    section.writes[EXPLORER] = text
    section.done.append("Pod / HoU columns read Unassigned instead of -1")
    return section


# ─────────────────────────────────────────────────────────────────────────────
# D. Tabs survive a refresh
# ─────────────────────────────────────────────────────────────────────────────

URL_TAB_SOURCE = """"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * A tab selection that survives a refresh, parked in the query string.
 *
 * Reading the URL happens in an effect off `window.location`, not through
 * `useSearchParams`, deliberately: `useSearchParams` drags the whole page into a
 * Suspense boundary at build time, and reading the URL during render makes the server
 * render and the first client render disagree. Starting on the fallback and correcting
 * on mount is the same shape the sidebar already uses for its collapsed state - one
 * frame of the default, then the real value, and never a hydration mismatch.
 *
 * A value the page does not recognise is ignored rather than trusted, so a mistyped
 * `?tab=xyz` lands on the default instead of rendering an empty page.
 *
 * The URL is updated with replaceState, not push: flicking through tabs should not
 * build a history stack the back button then has to walk out of one step at a time.
 */
export function useUrlTab<T extends string>(
  key: string,
  allowed: readonly T[],
  fallback: T,
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(fallback);

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get(key);
    if (raw !== null && (allowed as readonly string[]).includes(raw)) {
      setValue(raw as T);
    }
    // `allowed` is an inline literal at the call sites, so a new array identity every
    // render would re-run this and fight the user's own tab clicks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const select = useCallback(
    (next: T) => {
      setValue(next);
      const url = new URL(window.location.href);
      url.searchParams.set(key, next);
      window.history.replaceState(null, "", url.toString());
    },
    [key],
  );

  return [value, select];
}
"""

TAB_STATE_RE = re.compile(
    r"const \[(?P<name>(?:[A-Za-z_][A-Za-z0-9_]*)?[Tt]ab)\s*,\s*(?P<setter>set[A-Za-z0-9_]*)\]"
    r"\s*=\s*useState<(?P<type>[^>]+)>\(\s*(?P<initial>\"[^\"]+\")\s*\)\s*;"
)
LITERAL_RE = re.compile(r'"([^"]+)"')


def resolve_union(type_expr: str, text: str) -> list[str] | None:
    """The string literals a tab type can hold - inline, or via `type X = "a" | "b";`."""
    expr = type_expr.strip()
    if '"' in expr:
        return LITERAL_RE.findall(expr)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expr):
        return None
    alias = re.search(rf"^type {re.escape(expr)}\s*=\s*([^;]+);", text, re.M)
    if alias is None or '"' not in alias.group(1):
        return None
    return LITERAL_RE.findall(alias.group(1))


def section_url_tabs() -> Section:
    section = Section("url-tabs")
    if URL_TAB_TS.exists() and URL_TAB_TS.read_text() != URL_TAB_SOURCE:
        section.done.append(f"rewriting {URL_TAB_TS} (contents differed)")
    if not (URL_TAB_TS.exists() and URL_TAB_TS.read_text() == URL_TAB_SOURCE):
        section.writes[URL_TAB_TS] = URL_TAB_SOURCE

    candidates = sorted(
        p
        for p in ROOT.glob("frontend/**/*.tsx")
        if "node_modules" not in p.parts and TAB_STATE_RE.search(p.read_text())
    )
    if not candidates:
        section.done.append(
            "no `const [tab, setTab] = useState<...>()` left to convert"
        )
        return section

    for path in candidates:
        text = path.read_text()
        matches = list(TAB_STATE_RE.finditer(text))
        if len(matches) != 1:
            section.skip(
                f"{path}: {len(matches)} tab states in one file - which one owns `?tab=` "
                "is a judgement call, not a patch",
                window(text, "useState<"),
            )
            continue
        match = matches[0]
        values = resolve_union(match.group("type"), text)
        if not values:
            section.skip(
                f"{path}: could not resolve `{match.group('type')}` to a set of string "
                "literals - refusing to guess which values are valid",
                window(text, match.group(0)[:40]),
            )
            continue
        initial = match.group("initial").strip('"')
        if initial not in values:
            section.skip(
                f"{path}: initial tab {initial!r} is not one of {values}",
                match.group(0),
            )
            continue

        literals = ", ".join(f'"{v}"' for v in values)
        head = f"const [{match.group('name')}, {match.group('setter')}] = "
        call = (
            f'useUrlTab<{match.group("type").strip()}>("tab", [{literals}], '
            f"{match.group('initial')});"
        )
        replacement = head + call
        if len(replacement) + 2 > 100:
            # Long unions would run off the edge of the screen on one line.
            replacement = (
                head
                + f"useUrlTab<{match.group('type').strip()}>(\n"
                + '    "tab",\n'
                + f"    [{literals}],\n"
                + f"    {match.group('initial')},\n"
                + "  );"
            )
        patched = text[: match.start()] + replacement + text[match.end() :]

        # Dropping the only useState in a file would orphan its import and fail lint.
        if "useState" not in patched and "useState" in text:
            section.skip(
                f"{path}: that was the file's only useState - the import would dangle"
            )
            continue

        patched = add_import(patched, 'import { useUrlTab } from "@/lib/use-url-tab";')
        section.writes[path] = patched
        section.done.append(
            f"{path}: ?tab= now survives a refresh ({'/'.join(values)})"
        )

    return section


# ─────────────────────────────────────────────────────────────────────────────
# E. Recon for the last four items
# ─────────────────────────────────────────────────────────────────────────────


def dump(
    title: str, path: Path, *, whole: bool = False, needles: tuple[str, ...] = ()
) -> None:
    print(f"\n--- {title} " + "-" * max(0, 66 - len(title)))
    if not path.exists():
        print(f"  MISSING: {path}")
        return
    lines = path.read_text().splitlines()
    print(f"  {path}  ({len(lines)} lines)")
    if whole:
        for i, line in enumerate(lines, 1):
            print(f"  {i:>4}  {line}")
        return
    wanted: set[int] = set()
    for i, line in enumerate(lines):
        if any(n in line for n in needles):
            wanted.update(range(max(0, i - 4), min(len(lines), i + 9)))
    last = -2
    for i in sorted(wanted):
        if i != last + 1:
            print("        ...")
        print(f"  {i + 1:>4}  {lines[i]}")
        last = i
    if not wanted:
        print(f"  (nothing matched {needles})")


def recon() -> None:
    print("\n" + "=" * 72)
    print("RECON (read-only) - what the last four items need")
    print("=" * 72)

    dump(
        "sidebar: order persistence",
        SIDEBAR,
        needles=("ORDER_KEY", "localStorage", "setOrder", "reorder", "applyOrder"),
    )

    glossary = [
        p
        for p in ROOT.glob("frontend/**/*")
        if p.is_file()
        and "glossary" in p.name.lower()
        and "node_modules" not in p.parts
    ]
    if glossary:
        for path in glossary:
            dump("glossary page (whole file - it is being rewritten)", path, whole=True)
    else:
        print("\n--- glossary page " + "-" * 49)
        print("  (no file with 'glossary' in its name)")

    for pattern, title, needles in (
        (
            "frontend/components/spotlight/*.tsx",
            "spotlight board",
            ("app-master", "router.push", "export function", "onClick", "Edit"),
        ),
        (
            "frontend/components/app-master/*.tsx",
            "app master (edit drawer + hooks)",
            ("EditDrawer", "export ", "primaryKey", "useAppMaster"),
        ),
    ):
        for path in sorted(ROOT.glob(pattern)):
            dump(title, path, needles=needles)

    dump(
        "attribution helpers (confirming dimensionLabel's signature)",
        ATTRIBUTION_TS,
        needles=("export ",),
    )


# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    if not (ROOT / "frontend").is_dir() or not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    for build in (
        section_allowed_pages,
        section_nav_order_hook,
        section_explorer_unassigned,
        section_url_tabs,
    ):
        build().commit()

    print(
        "PATCHED, NOT YET VERIFIED - the test run is the verification, not this script."
    )
    for note in notes:
        print(f"  - {note}")
    for entry in skipped:
        print()
        print(entry)

    recon()
    # Skipped sections are reported, not fatal: the sections that DID apply are real work
    # and the build has to run over them either way.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

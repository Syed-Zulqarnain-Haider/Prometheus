#!/usr/bin/env python3
"""Frontend batch 1: the sidebar, the orphan routes, Unassigned pods, and the averages.

Five changes, each anchored to source read off this server rather than guessed:

  1. Sidebar grouping. GROUPS in sidebar.tsx never listed /today, /apps-admin or
     /pod-owners, so all three fell into the "More" catch-all - which is why the
     sidebar looked like it had lost pages. It also still listed /app-master,
     /app-changes and /spotlight, which are no longer in the nav at all.

  2. The three orphan routes become redirects to /apps-admin, where they were
     merged. They are still reachable today and render the OLD pre-merge pages,
     so the same data has two homes and only one of them gets fixed.

  3. Pod -1 is accepted by the App Master editor. The server already accepts it
     (unassigned apps and new arrivals live there); the form still refused, so
     un-assigning an app was impossible from the UI.

  4. YTD and MTD show their averages as NUMBERS, alongside the totals, instead
     of only as a smoothing option on the trend line.

  5. A test that fails when a page exists but no sidebar entry reaches it, or a
     nav entry points at a page that does not exist, or a nav entry belongs to no
     sidebar group. That is the class of fault behind "why is it missing pages" -
     it should not depend on someone noticing.

Nothing is written unless every anchor resolves exactly once. Re-running is a no-op.
Reverting is: git checkout -- frontend/
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"

SIDEBAR = FE / "components" / "layout" / "sidebar.tsx"
APP_MASTER = FE / "components" / "app-master" / "app-master-client.tsx"
PROGRESS = FE / "components" / "overview" / "revenue-progress.tsx"
METADATA = FE / "components" / "app-detail" / "metadata-card.tsx"
APPS_ADMIN = FE / "components" / "apps-admin" / "apps-admin-client.tsx"
NAV_TEST = FE / "tests" / "nav-coverage.test.ts"

problems: list[str] = []
notes: list[str] = []
writes: dict[Path, str] = {}


def fail(message: str) -> None:
    problems.append(message)


def note(message: str) -> None:
    notes.append(message)


def read(path: Path) -> str | None:
    if not path.exists():
        fail(f"missing: {path.relative_to(ROOT)}")
        return None
    return path.read_text(encoding="utf-8")


def swap(path: Path, source: str, old: str, new: str, what: str) -> str | None:
    """Replace `old` with `new`, requiring exactly one match."""
    count = source.count(old)
    if count != 1:
        fail(f"{path.relative_to(ROOT)}: {what} matched {count} times, expected 1")
        window = old.strip().splitlines()[0][:70]
        for number, line in enumerate(source.splitlines(), 1):
            if window and window in line:
                print(f"    on disk near {path.relative_to(ROOT)}:{number}: {line}")
        return None
    note(f"{path.relative_to(ROOT)}: {what}")
    return source.replace(old, new, 1)


def add_import(source: str, statement: str) -> str:
    """Insert an import after the last existing one. Idempotent."""
    if statement in source:
        return source
    ends = [m.end() for m in re.finditer(r'^(?:import [^\n]*?;|\} from "[^"]+";)$', source, re.M)]
    if not ends:
        fail("could not find an import block to extend")
        return source
    cut = max(ends)
    return source[:cut] + "\n" + statement + source[cut:]


# ── 1. sidebar grouping ──────────────────────────────────────────────────────
OLD_GROUPS = '''const GROUPS: { title: string; hrefs: string[] }[] = [
  { title: "Overview", hrefs: ["/overview", "/compare"] },
  { title: "Performance", hrefs: ["/revenue", "/ua", "/store"] },
  { title: "Apps", hrefs: ["/apps", "/explore", "/app-master", "/app-changes", "/spotlight"] },
  { title: "Reporting", hrefs: ["/reports", "/glossary"] },
  { title: "People", hrefs: ["/chat", "/profile"] },
];'''

NEW_GROUPS = '''const GROUPS: { title: string; hrefs: string[] }[] = [
  { title: "Overview", hrefs: ["/today", "/overview", "/compare"] },
  { title: "Performance", hrefs: ["/revenue", "/ua", "/store"] },
  { title: "Apps", hrefs: ["/apps", "/explore", "/apps-admin"] },
  { title: "Reporting", hrefs: ["/reports", "/glossary"] },
  { title: "People", hrefs: ["/pod-owners", "/chat", "/profile"] },
];'''


def patch_sidebar() -> None:
    source = read(SIDEBAR)
    if source is None:
        return
    if '"/apps-admin"' in source and '"/today"' in source:
        note("sidebar.tsx already groups every page - left as is.")
        return
    out = swap(SIDEBAR, source, OLD_GROUPS, NEW_GROUPS, "grouped Today, Apps and Pod Owners")
    if out is not None:
        writes[SIDEBAR] = out


# ── 2. orphan routes -> redirects ────────────────────────────────────────────
def discover_tabs() -> dict[str, str]:
    """Map an old route to the /apps-admin tab that replaced it, read from the client."""
    source = APPS_ADMIN.read_text(encoding="utf-8") if APPS_ADMIN.exists() else ""
    ids = re.findall(r'\bid:\s*"([a-z0-9-]+)"', source)
    note(f"apps-admin tab ids found: {ids or 'none'}")

    def pick(*words: str) -> str:
        for identifier in ids:
            if any(word in identifier for word in words):
                return f"?tab={identifier}"
        return ""

    return {
        "spotlight": pick("spotlight", "needs", "fix"),
        "app-master": pick("master", "record", "app-master"),
        "app-changes": pick("change", "propos", "request"),
    }


REDIRECT = '''import {{ redirect }} from "next/navigation";

/** Merged into /apps-admin - kept as a redirect rather than deleted.
 *
 *  This URL is in people's history, bookmarks and older shared links. Leaving the old
 *  page mounted meant the same records had two homes and only one of them got fixed;
 *  deleting it outright would answer an existing link with a 404, which reads as the
 *  feature having been removed rather than moved. */
export default function {component}() {{
  redirect("/apps-admin{query}");
}}
'''


def patch_routes() -> None:
    tabs = discover_tabs()
    for slug, component in (
        ("spotlight", "SpotlightPage"),
        ("app-master", "AppMasterPage"),
        ("app-changes", "AppChangesPage"),
    ):
        page = FE / "app" / "(app)" / slug / "page.tsx"
        source = read(page)
        if source is None:
            continue
        if "redirect(" in source:
            note(f"{page.relative_to(ROOT)} already redirects - left as is.")
            continue
        writes[page] = REDIRECT.format(component=component, query=tabs[slug])
        note(f"{page.relative_to(ROOT)} -> /apps-admin{tabs[slug] or ''}")


# ── 3. pod -1 in the App Master editor ───────────────────────────────────────
OLD_GUARD = '''    // Client-side guards matching the backend: pod > 0, net_revenue_share in [0.0, 1.0].
    const podRaw = String(form["pod"] ?? "").trim();
    if (podRaw !== "") {
      const n = Number(podRaw);
      if (!Number.isInteger(n) || n <= 0) {
        setLocalError("Pod must be a whole number greater than 0.");
        return;
      }
    }'''

NEW_GUARD = '''    // Client-side guards matching the backend: a pod is a positive whole number, OR the
    // unassigned bucket. -1 is a real, meaningful value - apps nobody owns yet and apps
    // that have just arrived in the feed live there, and they carry real revenue - so the
    // form has to be able to express it. Refusing it here made un-assigning an app
    // impossible from the UI even though the API accepts it.
    const podRaw = String(form["pod"] ?? "").trim();
    if (podRaw !== "") {
      const n = Number(podRaw);
      const unassigned = Number(UNASSIGNED_POD);
      if (!Number.isInteger(n) || (n <= 0 && n !== unassigned)) {
        setLocalError(
          `Pod must be a whole number greater than 0, or ${unassigned} for unassigned.`,
        );
        return;
      }
    }'''

OLD_POD_INPUT = '''              ) : c.name === "pod" ? (
                <Input
                  id={`f-${c.name}`}
                  type="number"
                  min={1}
                  step={1}
                  value={String(form[c.name] ?? "")}
                  onChange={(e) => setForm((f) => ({ ...f, [c.name]: e.target.value }))}
                  placeholder="Pod number (> 0)"
                />'''

NEW_POD_INPUT = '''              ) : c.name === "pod" ? (
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Input
                      id={`f-${c.name}`}
                      type="number"
                      step={1}
                      value={String(form[c.name] ?? "")}
                      onChange={(e) => setForm((f) => ({ ...f, [c.name]: e.target.value }))}
                      placeholder={`Pod number, or ${UNASSIGNED_POD} for unassigned`}
                    />
                    {/* An explicit control rather than expecting anyone to know that -1 is
                        the unassigned bucket. Typing it still works. */}
                    <button
                      type="button"
                      onClick={() =>
                        setForm((f) => ({
                          ...f,
                          [c.name]:
                            String(f[c.name] ?? "") === UNASSIGNED_POD ? "" : UNASSIGNED_POD,
                        }))
                      }
                      aria-pressed={String(form[c.name] ?? "") === UNASSIGNED_POD}
                      className={cn(
                        "shrink-0 rounded-md border px-2.5 py-1.5 text-xs transition-colors",
                        String(form[c.name] ?? "") === UNASSIGNED_POD
                          ? "border-[color:var(--color-accent)] bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)]"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground",
                      )}
                    >
                      {UNASSIGNED_LABEL}
                    </button>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {UNASSIGNED_LABEL} ({UNASSIGNED_POD}) is where apps nobody owns yet and new
                    apps from the feed sit. They still carry revenue.
                  </p>
                </div>'''


def patch_app_master() -> None:
    source = read(APP_MASTER)
    if source is None:
        return
    if "UNASSIGNED_POD" in source:
        note("app-master-client.tsx already accepts the unassigned pod - left as is.")
        return
    out = swap(APP_MASTER, source, OLD_GUARD, NEW_GUARD, "pod validation accepts unassigned")
    if out is None:
        return
    out2 = swap(APP_MASTER, out, OLD_POD_INPUT, NEW_POD_INPUT, "pod input offers Unassigned")
    if out2 is None:
        return
    out2 = add_import(out2, 'import { UNASSIGNED_LABEL, UNASSIGNED_POD } from "@/lib/attribution";')
    if "from \"@/lib/utils\"" not in out2:
        out2 = add_import(out2, 'import { cn } from "@/lib/utils";')
    writes[APP_MASTER] = out2


# ── 4. YTD / MTD averages as numbers ─────────────────────────────────────────
# `const option: EChartsOption = {` occurs twice in this file - the progress donut and
# the trend chart below it. Anchor on pacePct, which is defined exactly once.
OLD_OPTION = """  const pacePct = isYear
    ? (targetSet && projected != null ? projected / (target as number) : null)
    : (pacing.data?.pace_pct ?? null);"""

NEW_OPTION = '''  const pacePct = isYear
    ? (targetSet && projected != null ? projected / (target as number) : null)
    : (pacing.data?.pace_pct ?? null);

  // Averages as plain figures, not only as a smoothing option on the trend line.
  // "Is this month any good" is answered by a number you can hold next to last month's,
  // not by the shape of a curve. Both are revenue-to-date divided by how much of the
  // period has elapsed, so they read the same way on day 3 as on day 300 - and they are
  // run-rate averages, which is why they are labelled per week / per month rather than
  // "weekly total".
  const elapsedDays = isYear ? getDayOfYear(now) : now.getDate();
  const perDay = elapsedDays > 0 ? actual / elapsedDays : null;
  const perWeek = perDay === null ? null : perDay * 7;
  const perMonth = perDay === null ? null : perDay * (getDaysInYear(now) / 12);
  // YTD reads best per week and per month; MTD per day and per week - a monthly average
  // inside a month that is at most 31 days long is just the total again.
  const firstAverage = isYear ? perWeek : perDay;
  const secondAverage = isYear ? perMonth : perWeek;'''

OLD_FIGURE = '''          <Figure
            label={isYear ? "YTD Revenue" : "MTD Revenue"}
            value={formatUSD(actual, { compact: true })}
          />'''

NEW_FIGURE = '''          <Figure
            label={isYear ? "YTD Revenue" : "MTD Revenue"}
            value={formatUSD(actual, { compact: true })}
          />
          <Figure
            label={isYear ? "Avg / week" : "Avg / day"}
            value={firstAverage != null ? formatUSD(firstAverage, { compact: true }) : "-"}
          />
          <Figure
            label={isYear ? "Avg / month" : "Avg / week"}
            value={secondAverage != null ? formatUSD(secondAverage, { compact: true }) : "-"}
          />'''


def patch_progress() -> None:
    source = read(PROGRESS)
    if source is None:
        return
    if "firstAverage" in source:
        note("revenue-progress.tsx already shows the averages as numbers - left as is.")
        return
    out = swap(PROGRESS, source, OLD_OPTION, NEW_OPTION, "computed the run-rate averages")
    if out is None:
        return
    out = swap(PROGRESS, out, OLD_FIGURE, NEW_FIGURE, "added two average rows to both cards")
    if out is None:
        return
    writes[PROGRESS] = out


# ── 5. one more bare -1 ──────────────────────────────────────────────────────
def patch_metadata() -> None:
    source = read(METADATA)
    if source is None:
        return
    if "podLabel" in source:
        note("metadata-card.tsx already labels the unassigned pod - left as is.")
        return
    out = swap(METADATA, source, "value={app.pod}", "value={podLabel(app.pod)}",
               "App Detail shows Unassigned instead of -1")
    if out is None:
        return
    writes[METADATA] = add_import(out, 'import { podLabel } from "@/lib/attribution";')


# ── 6. the coverage test ─────────────────────────────────────────────────────
NAV_TEST_SOURCE = '''/**
 * Every page reachable, every nav entry real, every entry in a section.
 *
 * The sidebar quietly stopped showing Today, Apps and Pod Owners: they existed as pages
 * and as nav entries, but the sidebar's GROUPS map had never been told about them, so
 * they fell into the "More" catch-all and looked lost. Nobody reports a page they cannot
 * see. These are the three ways that can happen, each pinned:
 *
 *   1. a page exists but no nav entry reaches it
 *   2. a nav entry points at a page that does not exist
 *   3. a nav entry belongs to no sidebar section
 *
 * Read from the filesystem on purpose: asserting against a hand-written list of routes
 * would need updating by exactly the person who forgot to update the nav.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { NAV_ITEMS } from "@/lib/nav";

const FRONTEND = fileURLToPath(new URL("../", import.meta.url));

/** Routes that are deliberately not in the sidebar. Each needs a reason. */
const NOT_IN_NAV: Record<string, string> = {
  "/login": "reached when signed out, when there is no sidebar to be in",
};

interface Page {
  route: string;
  redirects: boolean;
}

/** Walk app/ and derive routes, dropping Next's (group) segments. */
function pages(directory: string, route = ""): Page[] {
  const found: Page[] = [];
  for (const entry of readdirSync(directory)) {
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) {
      // (group) segments organise files; they are not part of the URL.
      const segment = entry.startsWith("(") && entry.endsWith(")") ? "" : `/${entry}`;
      found.push(...pages(full, route + segment));
    } else if (entry === "page.tsx") {
      found.push({ route: route || "/", redirects: readFileSync(full, "utf8").includes("redirect(") });
    }
  }
  return found;
}

const ALL = pages(join(FRONTEND, "app"));
// Dynamic routes are reached from a table or a link, never from the sidebar.
const STATIC = ALL.filter((page) => !page.route.includes("["));

describe("navigation covers the app", () => {
  it("found the pages at all", () => {
    // Without this the rest passes vacuously if the walk ever returns nothing.
    expect(STATIC.length).toBeGreaterThan(10);
  });

  it("reaches every page from the sidebar", () => {
    const hrefs = new Set(NAV_ITEMS.map((item) => item.href));
    const unreachable = STATIC.filter(
      (page) =>
        !page.redirects &&
        page.route !== "/" &&
        !hrefs.has(page.route) &&
        !(page.route in NOT_IN_NAV),
    ).map((page) => page.route);
    expect(unreachable, `pages with no sidebar entry: ${unreachable.join(", ")}`).toEqual([]);
  });

  it("points every nav entry at a page that exists", () => {
    const routes = new Set(ALL.map((page) => page.route));
    const dangling = NAV_ITEMS.filter((item) => !routes.has(item.href)).map((item) => item.href);
    expect(dangling, `nav entries with no page: ${dangling.join(", ")}`).toEqual([]);
  });

  it("puts every nav entry in exactly one sidebar section", () => {
    // Read the sidebar's own maps rather than duplicating them: a copy here would go
    // stale in precisely the situation this test exists to catch.
    const sidebar = readFileSync(join(FRONTEND, "components/layout/sidebar.tsx"), "utf8");
    const maps = sidebar.slice(
      sidebar.indexOf("const GROUPS"),
      sidebar.indexOf("const FALLBACK_TITLE"),
    );
    expect(maps.length, "could not find the GROUPS/ADMIN_GROUP maps in sidebar.tsx").toBeGreaterThan(
      50,
    );
    const grouped = maps.match(/"\\/[a-z0-9-]*"/g)?.map((quoted) => quoted.slice(1, -1)) ?? [];

    for (const item of NAV_ITEMS) {
      const times = grouped.filter((href) => href === item.href).length;
      expect(times, `${item.href} appears in ${times} sidebar sections, expected exactly 1`).toBe(
        1,
      );
    }
    // And the reverse: a section listing a route that no longer exists in the nav leaves
    // a dead entry that silently does nothing.
    const known = new Set(NAV_ITEMS.map((item) => item.href));
    const dead = grouped.filter((href) => !known.has(href));
    expect(dead, `sidebar sections list routes that are not in the nav: ${dead.join(", ")}`).toEqual(
      [],
    );
  });
});
'''


# ── recon tail ───────────────────────────────────────────────────────────────
def recon() -> None:
    print("\n" + "=" * 78)
    print("== recon for the NEXT batch (Spotlight inline edit, chat chips, rest of -1)")
    print("=" * 78)
    targets = [
        (APP_MASTER, 60, 100, "EditDrawer signature + props"),
        (APP_MASTER, 355, 400, "the pod filter and where podOpts comes from"),
        (FE / "components" / "spotlight" / "spotlight-client.tsx", 200, 369, "tiles + edit link"),
        (FE / "components" / "chat" / "chat-widget.tsx", 160, 226, "where SUGGESTIONS render"),
        (FE / "components" / "overview" / "splits.tsx", 1, 120, "BreakdownPie - pod donut labels"),
        (FE / "components" / "explore" / "explore-client.tsx", 1, 130, "Explore row rendering"),
        (FE / "components" / "revenue" / "revenue-drill.tsx", 40, 120, "drill row rendering"),
    ]
    for path, first, last, why in targets:
        if not path.exists():
            print(f"\n--- {path.relative_to(ROOT)}: missing")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        last = min(last, len(lines))
        print(f"\n--- {path.relative_to(ROOT)}  [{first}-{last} of {len(lines)}]  ({why})")
        for number in range(first, last + 1):
            print(f"{number:5}: {lines[number - 1]}")

    print("\n--- how a text column renders a cell in Apps Explorer")
    explorer = FE / "components" / "apps" / "apps-explorer.tsx"
    if explorer.exists():
        lines = explorer.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            if re.search(r'kind === "text"|render|formatCell|cell\(', line):
                print(f"{number:5}: {line}")


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    patch_sidebar()
    patch_routes()
    patch_app_master()
    patch_progress()
    patch_metadata()

    if not NAV_TEST.exists() or "appears in" not in NAV_TEST.read_text(encoding="utf-8"):
        writes[NAV_TEST] = NAV_TEST_SOURCE
        note("wrote frontend/tests/nav-coverage.test.ts")

    if problems:
        report()
        return 1

    for path, text in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    report()
    recon()
    return 1 if problems else 0


def report() -> None:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED - nothing was written:")
        for line in problems:
            print(f"  - {line}")
    else:
        print(f"\nPATCHED {len(writes)} file(s). Verified only by:")
        print("  ./scripts/run-frontend-tests.sh")


if __name__ == "__main__":
    raise SystemExit(main())

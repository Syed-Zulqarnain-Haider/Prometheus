#!/usr/bin/env python3
"""UX batch 6: Spotlight opens the editor instead of navigating away, and the glossary
gets back the distinction the old one led with.

What the last run taught us, and what this does about it:

  A. SPOTLIGHT.  The board is a wall of links: clicking a tile NAVIGATES to App Master
     with a search term. That is precisely the complaint - you lose the board, your
     filter and your place, to change one field. For admins the click now opens the app
     editor over the board instead. The href stays exactly as it was, so middle-click and
     "open in new tab" still go to App Master, and non-admins still land on App Changes
     where they propose the edit rather than making it.

  B. THE DRAWER'S ROW MATCH.  It looked the row up by App Master's declared primary key
     alone. Spotlight knows apps by canonical_key, which may or may not BE that key, so
     the match now also accepts canonical_key / app_key. Matching stays exact - a search
     that returns something similar is not the same app, and silently editing the wrong
     record would be far worse than saying it could not be found.

  C. THE GLOSSARY'S MISSING FAMILY.  The page I replaced led with "Reported vs Modeled",
     covering the rpt_* columns - and those columns are not in the registry copy I wrote
     the new one from, so the rewrite dropped the single most important distinction on
     the page. That section goes back in, in plain language, along with the rule that
     says which number to quote. Inserted into the existing data file rather than
     rewriting it, so it does not matter whether batch 4 runs again afterwards.

  D. RECON for what is still guesswork: the Apps Explorer cell renderer (its "-1" fix
     could not match), the four App Changes mutations that never invalidate anything, and
     the real metric registry - so the rpt_* terms can be completed from the source of
     truth rather than from memory of one screenful.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")
SPOTLIGHT = ROOT / "frontend/components/spotlight/spotlight-client.tsx"
DRAWER = ROOT / "frontend/components/apps/app-edit-drawer.tsx"
GLOSSARY_DATA = ROOT / "frontend/lib/glossary-data.ts"
EXPLORER = ROOT / "frontend/components/apps/apps-explorer.tsx"
API_HOOKS = ROOT / "frontend/lib/api-hooks.ts"
REGISTRY = ROOT / "backend/app/core/metric_registry.py"

skipped: list[str] = []
notes: list[str] = []


class Section:
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
            path.write_text(text)
        for line in self.done or ["already applied - left alone"]:
            notes.append(f"[{self.name}] {line}")


def indent(text: str) -> str:
    return "\n".join(f"      | {line}" for line in text.rstrip("\n").splitlines())


def window(text: str, needle: str, before: int = 4, after: int = 14) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(lines[max(0, i - before) : i + after])
    return "(not found anywhere in the file)"


def add_import(text: str, statement: str) -> str:
    if statement in text:
        return text
    imports = list(re.finditer(r"^import [^\n]*;$", text, re.M))
    if not imports:
        return statement + "\n" + text
    end = imports[-1].end()
    return text[:end] + "\n" + statement + text[end:]


# ─────────────────────────────────────────────────────────────────────────────
# A. Spotlight: open the editor rather than leaving the board
# ─────────────────────────────────────────────────────────────────────────────

HREF_RE = re.compile(r"(?P<indent>[ \t]*)href=\{editHref\}\n")
EDITOR_IMPORT = 'import { openAppEditor } from "@/components/apps/app-edit-portal";'

INTERCEPT = """{indent}// Admins edit HERE. The href is left exactly as it was, so middle-click and
{indent}// "open in new tab" still reach App Master - only the plain click is taken
{indent}// over, and it opens the editor over the board instead of replacing it.
{indent}// Non-admins keep the App Changes route: they propose, they do not write.
{indent}onClick={{
{indent}  isAdmin
{indent}    ? (event) => {{
{indent}        event.preventDefault();
{indent}        openAppEditor(app.canonical_key);
{indent}      }}
{indent}    : undefined
{indent}}}
"""


def section_spotlight() -> Section:
    section = Section("spotlight-inline-edit")
    if not SPOTLIGHT.exists():
        section.skip(f"missing {SPOTLIGHT}")
        return section
    if not (ROOT / "frontend/components/apps/app-edit-portal.tsx").exists():
        section.skip("the app editor is not there yet - run ux-batch-4.py first")
        return section

    text = SPOTLIGHT.read_text()
    if "openAppEditor(" in text:
        return section

    hits = list(HREF_RE.finditer(text))
    if len(hits) != 1:
        section.skip(
            f"expected exactly one `href={{editHref}}` in the board tile, found {len(hits)}",
            window(text, "editHref"),
        )
        return section
    if "isAdmin" not in text or "app.canonical_key" not in text:
        section.skip(
            "the tile does not have both `isAdmin` and `app.canonical_key` in scope",
            window(text, "editHref"),
        )
        return section

    match = hits[0]
    text = (
        text[: match.end()]
        + INTERCEPT.format(indent=match.group("indent"))
        + text[match.end() :]
    )
    text = add_import(text, EDITOR_IMPORT)
    section.writes[SPOTLIGHT] = text
    section.done.append("an admin clicking a tile now edits it in place")
    return section


# ─────────────────────────────────────────────────────────────────────────────
# B. The drawer: find the row by any of the keys an app is known by
# ─────────────────────────────────────────────────────────────────────────────

OLD_MATCH = """    return (
      query.data.rows.find((r) => String(r[query.data.primary_key] ?? "") === appKey) ?? null
    );"""
NEW_MATCH = """    // App Master declares its own primary key, but callers know an app by whatever
    // identifier their screen happens to hold - Spotlight uses canonical_key. Accept any
    // of them, and keep the comparison EXACT: a search returning something similar is a
    // different app, and quietly editing the wrong record beats every other failure for
    // damage done.
    const keys = [query.data.primary_key, "canonical_key", "app_key", "android_package"];
    return (
      query.data.rows.find((r) =>
        keys.some((k) => k !== undefined && String(r[k] ?? "") === appKey),
      ) ?? null
    );"""


def section_drawer_match() -> Section:
    section = Section("drawer-row-match")
    if not DRAWER.exists():
        section.skip(f"missing {DRAWER} - run ux-batch-4.py first")
        return section
    text = DRAWER.read_text()
    if "const keys = [query.data.primary_key" in text:
        return section
    if text.count(OLD_MATCH) != 1:
        section.skip(
            "the drawer's row lookup is not the one this patch expects",
            window(text, "primary_key"),
        )
        return section
    section.writes[DRAWER] = text.replace(OLD_MATCH, NEW_MATCH, 1)
    section.done.append(
        "the drawer finds a row by canonical_key too, still matching exactly"
    )
    return section


# ─────────────────────────────────────────────────────────────────────────────
# C. The glossary: put Reported vs Modeled back
# ─────────────────────────────────────────────────────────────────────────────

RULES_ANCHOR = "export const RULES: { title: string; body: string }[] = [\n"
REPORTED_RULE = """  {
    title: "Two families of numbers, and which one to quote",
    body: "Reported figures (their names start with rpt_) are the finance-authoritative totals. They are calculated upstream and passed through untouched, and they are what the headline cards show - quote those. Modeled figures are the platform's own arithmetic over the raw signals, and they exist so you can break a number down per app, per pod, per day. When the two disagree, reported is the number that is right and modeled is the one that tells you where it came from.",
  },
"""

SECTIONS_ANCHOR = "export const SECTIONS: Section[] = [\n"
REPORTED_SECTION = """  {
    id: "reported",
    title: "Reported figures",
    blurb:
      "The finance-authoritative P&L, calculated upstream and passed through without the dashboard touching it. These are the headline numbers and the ones to quote outside the team.",
    terms: [
      {
        name: "rpt_gross_revenue_usd",
        label: "Gross revenue (reported)",
        plain: "Everything earned before any deduction, as finance states it.",
      },
      {
        name: "rpt_total_cost_usd",
        label: "Total cost (reported)",
        plain: "Everything deducted on the way from gross to profit - marketing, running costs, taxes, store and processing fees, and anything owed to a partner.",
      },
      {
        name: "rpt_net_profit_usd",
        label: "Net profit (reported)",
        plain: "What is left after every one of those deductions. The bottom line.",
        formula: "gross revenue - total cost",
      },
      {
        name: "rpt_net_revenue_terafort_usd",
        label: "Terafort net revenue",
        plain: "Our share of the net, once a partner's share has been paid out. On a wholly-owned app this is the whole of it; on a partnered one it is not, which is why the two are reported separately.",
      },
      {
        name: "total_revenue_usd",
        label: "Revenue (modeled)",
        plain: "The platform's own revenue figure, built from purchases and ad money. Use it to break revenue down by app, pod or day - that is what it is for. For a number going into a report, use gross revenue above.",
        formula: "IAP net + ad revenue",
      },
      {
        name: "profit_usd",
        label: "Profit (modeled)",
        plain: "The platform's own profit figure. It knows about marketing and tech cost but not about taxes, fees or partner shares, so it reads higher than reported net profit - by design, not by error.",
        formula: "total revenue - UA spend - tech cost",
      },
    ],
  },
"""


def section_glossary_reported() -> Section:
    section = Section("glossary-reported")
    if not GLOSSARY_DATA.exists():
        section.skip(f"missing {GLOSSARY_DATA} - run ux-batch-4.py first")
        return section
    text = GLOSSARY_DATA.read_text()
    if 'id: "reported"' in text:
        return section

    for label, anchor, block in (
        ("the rule", RULES_ANCHOR, REPORTED_RULE),
        ("the section", SECTIONS_ANCHOR, REPORTED_SECTION),
    ):
        if text.count(anchor) != 1:
            section.skip(
                f"could not find {label}'s anchor exactly once in {GLOSSARY_DATA}",
                window(text, anchor.split("\n")[0]),
            )
            return section
        index = text.index(anchor) + len(anchor)
        text = text[:index] + block + text[index:]

    section.writes[GLOSSARY_DATA] = text
    section.done.append(
        "Reported vs Modeled is back, as the first section and the first rule"
    )
    return section


# ─────────────────────────────────────────────────────────────────────────────
# D. Recon for what is still guesswork
# ─────────────────────────────────────────────────────────────────────────────

CHANGE_HOOKS = (
    "useProposeChange",
    "useApproveChange",
    "useRejectChange",
    "useCancelChange",
    "useRevokeSessions",
    "useRunScheduleNow",
    "useSaveDashboardLayout",
    "useResetDashboardLayout",
)


def recon() -> None:
    print("\n" + "=" * 72)
    print("RECON (read-only)")
    print("=" * 72)

    print("\n--- Apps Explorer: the whole column builder ------------------------")
    if EXPLORER.exists():
        text = EXPLORER.read_text()
        start = text.find("function buildColumns")
        if start == -1:
            print("  (no buildColumns function)")
        else:
            end = text.find("\nexport function", start)
            body = text[start : end if end != -1 else start + 4000]
            offset = text[:start].count("\n")
            for i, line in enumerate(body.splitlines(), offset + 1):
                print(f"  {i:>4}  {line}")
    else:
        print(f"  MISSING: {EXPLORER}")

    print("\n--- The mutations that never invalidate anything -------------------")
    if API_HOOKS.exists():
        text = API_HOOKS.read_text()
        for name in CHANGE_HOOKS:
            match = re.search(rf"^export function {name}\(", text, re.M)
            if match is None:
                print(f"\n  ({name} not found)")
                continue
            end = text.find("\nexport function ", match.end())
            body = text[match.start() : end if end != -1 else len(text)]
            offset = text[: match.start()].count("\n")
            print()
            for i, line in enumerate(body.rstrip().splitlines(), offset + 1):
                print(f"  {i:>4}  {line}")
    else:
        print(f"  MISSING: {API_HOOKS}")

    print("\n--- The metric registry (the rpt_* family the glossary needs) ------")
    if REGISTRY.exists():
        for i, line in enumerate(REGISTRY.read_text().splitlines(), 1):
            print(f"  {i:>4}  {line}")
    else:
        print(f"  MISSING: {REGISTRY}")


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    for build in (section_spotlight, section_drawer_match, section_glossary_reported):
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

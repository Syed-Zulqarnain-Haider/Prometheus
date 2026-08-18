#!/usr/bin/env python3
"""Bring the Overview to life: welcome hero, entrance choreography, responsive surfaces.

From the owner's inspiration boards (the friendly task-manager welcome banner, soft
drifting colour, cards that feel touchable). Everything is theme tokens, so it reads
correctly on every theme, and every animation respects prefers-reduced-motion.

  frontend/app/globals.css
      The motion vocabulary: `rise-in` (entrance - fade up 10px, ease-out), applied via
      .anim-rise; `hero-drift` for the greeting hero's blurred colour blobs. One
      reduced-motion block turns all of it off.

  frontend/components/overview/overview-client.tsx
      The static "Executive Overview" PageHeader becomes <GreetingHero /> - the
      dashboard greets the viewer by name with the date, over slowly drifting colour.

  frontend/components/overview/kpi-row.tsx
      Both KPI rows cascade in, 60ms apart per card (the ladder row continues the
      sequence after the first five), so the page composes itself instead of popping.

  frontend/components/overview/dashboard-grid.tsx
      Each widget rises in on mount. The class sits on the INNER measured div - the
      outer one is positioned by react-grid-layout via transform, and animating that
      one would fight the layout engine.

  frontend/components/ui/card.tsx
      Cards deepen their shadow on hover. Shadow only, deliberately no translate: a
      lift would jiggle table rows mid-read and fight the grid editor's dragging.

Requires frontend/components/overview/greeting-hero.tsx to be checked out first.
Anchored: every anchor must appear EXACTLY once or nothing is written - all files
validate before any is touched. Idempotent. Frontend rebuild; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

GLOBALS = Path("frontend/app/globals.css")
CLIENT = Path("frontend/components/overview/overview-client.tsx")
KPI_ROW = Path("frontend/components/overview/kpi-row.tsx")
GRID = Path("frontend/components/overview/dashboard-grid.tsx")
CARD = Path("frontend/components/ui/card.tsx")
HERO = Path("frontend/components/overview/greeting-hero.tsx")

# ── globals.css ───────────────────────────────────────────────────────────────
CSS_ANCHOR = """  h1,
  h2,
  h3 {
    font-family: var(--font-display);
  }
}
"""
CSS_ADD = """
/* ── Motion vocabulary (scripts/beautify-overview-motion.py) ─────────────────────
   Entrances + the greeting hero's ambient drift. Reduced motion turns it all off. */
@keyframes rise-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.anim-rise {
  animation: rise-in 480ms cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes hero-drift {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(-2.5rem, 1.25rem, 0) scale(1.15); }
}
.hero-blob {
  animation: hero-drift 14s ease-in-out infinite alternate;
}
@media (prefers-reduced-motion: reduce) {
  .anim-rise,
  .hero-blob {
    animation: none;
  }
}
"""

# ── overview-client.tsx ───────────────────────────────────────────────────────
CLIENT_IMPORT_ANCHOR = 'import { PageHeader } from "@/components/layout/page-header";\n'
CLIENT_IMPORT_NEW = 'import { GreetingHero } from "@/components/overview/greeting-hero";\n'

CLIENT_MOUNT_ANCHOR = '        <PageHeader title="Executive Overview" />\n'
CLIENT_MOUNT_NEW = "        <GreetingHero />\n"

# ── kpi-row.tsx (two identical blocks, distinguished by the mapped list) ──────
def kpi_block(list_name: str) -> str:
    return f"""        {{{list_name}.map((kpi) => (
          <KpiCard
            key={{kpi.field}}
            label={{kpi.label}}
            value={{kpi.value}}
            current={{kpi.current}}
            previous={{kpi.previous}}
            spark={{kpi.spark}}
            description={{kpi.description}}
            loading={{loading}}
          />
        ))}}
"""


def kpi_block_new(list_name: str, base_delay: int) -> str:
    return f"""        {{{list_name}.map((kpi, index) => (
          <div
            key={{kpi.field}}
            className="anim-rise"
            style={{{{ animationDelay: `${{{base_delay} + index * 60}}ms` }}}}
          >
            <KpiCard
              label={{kpi.label}}
              value={{kpi.value}}
              current={{kpi.current}}
              previous={{kpi.previous}}
              spark={{kpi.spark}}
              description={{kpi.description}}
              loading={{loading}}
            />
          </div>
        ))}}
"""


# ── dashboard-grid.tsx ────────────────────────────────────────────────────────
GRID_ANCHOR = '    <div ref={ref} className={editable ? "pointer-events-none select-none" : undefined}>\n'
# anim-rise on the INNER div: the outer one is positioned by react-grid-layout via
# transform, and animating that would fight the layout engine. (No comment in the
# emitted code - this div is the root of a return(), where a JSX comment is invalid.)
GRID_NEW = '    <div ref={ref} className={editable ? "anim-rise pointer-events-none select-none" : "anim-rise"}>\n'

# ── ui/card.tsx ───────────────────────────────────────────────────────────────
CARD_ANCHOR = '      className={cn("rounded-lg border bg-card text-card-foreground shadow-card", className)}\n'
CARD_NEW = (
    "      // Shadow only on hover - a translate lift would jiggle table rows mid-read\n"
    "      // and fight the grid editor's dragging.\n"
    '      className={cn(\n'
    '        "rounded-lg border bg-card text-card-foreground shadow-card transition-shadow duration-200 hover:shadow-lg",\n'
    "        className,\n"
    "      )}\n"
)


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def require_once(path: Path, text: str, anchor: str) -> None:
    if text.count(anchor) != 1:
        first = anchor.splitlines()[0].strip()
        die(f"{path}: expected exactly one {first!r}, found {text.count(anchor)}")


def main() -> None:
    for path in (GLOBALS, CLIENT, KPI_ROW, GRID, CARD):
        if not path.exists():
            die(f"{path} not found - run from the repository root")
    if not HERO.exists():
        die(f"{HERO} not found - check it out before running this")

    files = {path: path.read_text() for path in (GLOBALS, CLIENT, KPI_ROW, GRID, CARD)}
    todo: dict[Path, str] = {}

    if ".anim-rise" in files[GLOBALS]:
        print(f"{GLOBALS}: motion vocabulary already present")
    else:
        require_once(GLOBALS, files[GLOBALS], CSS_ANCHOR)
        todo[GLOBALS] = files[GLOBALS].replace(CSS_ANCHOR, CSS_ANCHOR + CSS_ADD, 1)

    if "GreetingHero" in files[CLIENT]:
        print(f"{CLIENT}: hero already mounted")
    else:
        require_once(CLIENT, files[CLIENT], CLIENT_IMPORT_ANCHOR)
        require_once(CLIENT, files[CLIENT], CLIENT_MOUNT_ANCHOR)
        text = files[CLIENT]
        text = text.replace(CLIENT_IMPORT_ANCHOR, CLIENT_IMPORT_NEW, 1)
        text = text.replace(CLIENT_MOUNT_ANCHOR, CLIENT_MOUNT_NEW, 1)
        todo[CLIENT] = text

    if "anim-rise" in files[KPI_ROW]:
        print(f"{KPI_ROW}: already cascades")
    else:
        for name in ("kpis", "ladder"):
            require_once(KPI_ROW, files[KPI_ROW], kpi_block(name))
        text = files[KPI_ROW]
        text = text.replace(kpi_block("kpis"), kpi_block_new("kpis", 0), 1)
        # The ladder row continues the cascade after the first five cards.
        text = text.replace(kpi_block("ladder"), kpi_block_new("ladder", 300), 1)
        todo[KPI_ROW] = text

    if "anim-rise" in files[GRID]:
        print(f"{GRID}: widgets already rise")
    else:
        require_once(GRID, files[GRID], GRID_ANCHOR)
        todo[GRID] = files[GRID].replace(GRID_ANCHOR, GRID_NEW, 1)

    if "hover:shadow-lg" in files[CARD]:
        print(f"{CARD}: already responsive to hover")
    else:
        require_once(CARD, files[CARD], CARD_ANCHOR)
        todo[CARD] = files[CARD].replace(CARD_ANCHOR, CARD_NEW, 1)

    if not todo:
        print("already beautiful - nothing to do")
        return

    for path, text in todo.items():
        path.write_text(text)
        print(f"patched {path}")

    print("\nRebuild the frontend: docker compose -f docker-compose.prod.yml up -d --build frontend")


if __name__ == "__main__":
    main()

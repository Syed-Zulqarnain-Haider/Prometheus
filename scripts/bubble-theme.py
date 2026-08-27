#!/usr/bin/env python3
"""One skin and one opacity dial for the three floating corner buttons.

The assistant, the privacy shield and the announcement button are three unrelated
components that each decided independently what a floating round button looks like: one
is the coral accent, one is elevated-surface grey, one is the primary fill, and two of
them dim themselves at rest by different amounts. Nothing coordinates them because
nothing ever had to.

WHAT THIS DOES
--------------
  1. Adds ``--color-bubble`` / ``--color-bubble-strong`` / ``--color-bubble-foreground``
     to the theme (light blue, one value per theme) and two classes, ``.tf-bubble``
     (resting opacity) and ``.tf-bubble-skin`` (the colour).
  2. Adds ONE admin-editable setting, ``bubble_opacity_pct``, to the settings registry.
     The System tab renders int settings generically, so it appears there by itself -
     no admin UI is written, and nothing can drift out of step with the registry.
  3. Publishes that number to the page as ``--tf-bubble-opacity`` from a component that
     renders nothing. The CSS carries its own fallback, so the buttons are never
     invisible while the setting loads, and are never invisible if it fails to load.
  4. Puts the two classes on each of the three buttons.

WHY CSS AND NOT PROPS
---------------------
Threading a number through three components that share no parent would mean three
prop chains and a fourth one the day a fourth bubble is added. A custom property on the
root element is read by anything wearing the class, so the next floating button inherits
the setting by existing.

The colour rules are deliberately UNLAYERED - after Tailwind's utilities in source
order - because the buttons' own ``bg-*`` and ``opacity-*`` utilities would otherwise
win. The now-dead utilities are stripped where they can be found, but the styling does
not depend on that having succeeded.

Sections are independent: each either applies completely or is skipped and reported.
Half of this is still an improvement; a half-applied SECTION would not be.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(".")

SETTING_KEY = "bubble_opacity_pct"
DEFAULT_PCT = 85
MIN_PCT = 20  # a bubble you cannot see is a bubble you cannot press
MAX_PCT = 100

report: list[str] = []
skipped: list[str] = []


# ── helpers ────────────────────────────────────────────────────────────────────────
def window(text: str, needle: str, before: int = 3, after: int = 10) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(f"      | {ln}" for ln in lines[max(0, i - before) : i + after])
    return "      | (not found in this file)"


class Swap:
    """One exact substring replacement that must match exactly once.

    ``required`` swaps carry the change; the rest are tidy-ups (removing utilities that
    the new CSS already overrides). A missed tidy-up is reported and costs nothing,
    because the appearance does not depend on it.
    """

    def __init__(self, old: str, new: str, *, required: bool = True, why: str = "") -> None:
        self.old, self.new, self.required, self.why = old, new, required, why


def ensure_after(label: str, path: Path, anchor: str, line: str, why: str) -> bool:
    """Make sure ``line`` sits exactly once, immediately after ``anchor``.

    Written this way after the first version of this script added a line by pattern and
    KEPT the pattern, so a second run added the line a second time - a repeated keyword
    argument, which is a syntax error, so nothing in the package could be imported at all.

    "Insert if a marker is absent" would not have been enough. That only stops the NEXT
    run; a file already double-written stays broken forever, and the fix has to be run by
    hand at exactly the moment nobody can run anything. So every existing copy is removed
    first and exactly one is put back: running this on a correct file changes nothing,
    running it on a doubled file repairs it.
    """
    if not path.exists():
        skipped.append(f"[{label}] {path} does not exist here - nothing changed.")
        return False
    text = path.read_text()
    if text.count(anchor) != 1:
        skipped.append(
            f"[{label}] {path}: expected exactly one anchor, found {text.count(anchor)}:\n"
            f"      {anchor.strip()[:150]}\n"
            "    on disk near it:\n" + window(text, anchor.strip()[:40])
        )
        return False

    before = text.count(line)
    cleaned = text.replace(line, "")
    if cleaned.count(anchor) != 1:
        skipped.append(
            f"[{label}] {path}: the anchor and the added line overlap, so removing one "
            "would damage the other. Nothing was changed."
        )
        return False

    at = cleaned.index(anchor) + len(anchor)
    path.write_text(cleaned[:at] + line + cleaned[at:])
    if before > 1:
        report.append(
            f"[{label}] {path}: REPAIRED - the line was there {before} times, now once ({why})"
        )
    elif before == 1:
        report.append(f"[{label}] {path}: already correct - {why}")
    else:
        report.append(f"[{label}] {path}: {why}")
    return True


def apply_swaps(label: str, path: Path, swaps: list[Swap], *, already: str = "") -> bool:
    """Replacements whose new text does not contain the old, so a second run finds
    nothing to do. ``already`` names what a finished file contains, so that second run
    says "already applied" rather than reporting every anchor as missing - the two look
    the same from outside and mean completely different things."""
    if not path.exists():
        skipped.append(f"[{label}] {path} does not exist here - nothing changed.")
        return False
    text = path.read_text()
    if already and already in text:
        report.append(f"[{label}] {path}: already applied - left alone")
        return True

    missing = [s for s in swaps if s.required and text.count(s.old) != 1]
    if missing:
        detail = "\n".join(
            f"    expected exactly one:\n      {s.old.strip()[:150]}\n"
            f"    on disk near it:\n{window(text, s.old.strip()[:40])}"
            for s in missing
        )
        skipped.append(f"[{label}] {path} - nothing changed.\n{detail}")
        return False

    done: list[str] = []
    for swap in swaps:
        if text.count(swap.old) != 1:
            report.append(f"[{label}] optional tidy-up not found, left as-is: {swap.why}")
            continue
        text = text.replace(swap.old, swap.new, 1)
        if swap.why:
            done.append(swap.why)
    path.write_text(text)
    report.append(f"[{label}] {path}: " + "; ".join(done))
    return True


# ── 1. the stylesheet ──────────────────────────────────────────────────────────────
CSS_START = "/* tf-bubble:start v2 - managed by scripts/bubble-theme.py */"
CSS_END = "/* tf-bubble:end */"
# The header of the FIRST version, which had no sentinels. Kept so a file already
# carrying that block can be replaced rather than appended to a second time.
CSS_V1_HEADER = "/* \u2500\u2500 tf-bubble: the floating corner buttons"

CSS = (
    CSS_START
    + """
/* The floating corner buttons - the assistant, the privacy shield and the announcement
   button - are three unrelated components. This is the one place that says what a
   floating button looks like, so changing the colour or the resting opacity is one edit
   here rather than three.

   --tf-bubble-opacity is written to the root element at runtime by <BubbleTheme /> from
   the admin setting. The fallback below is what renders before that resolves, and if it
   never resolves - so these can never come up invisible.

   These rules are deliberately OUTSIDE any @layer. The buttons carry Tailwind
   background and opacity utilities of their own, and coming after those in source order
   is what lets these win without an !important on every line. */
:root {
  --color-bubble: #8ecae6;
  --color-bubble-strong: #5fb0d8;
  --color-bubble-foreground: #0d2130;
  --tf-bubble-opacity: 0.85;
}
:root[data-theme="light"] {
  --color-bubble: #7cbede;
  --color-bubble-strong: #4a9ecb;
  --color-bubble-foreground: #06121b;
}

.tf-bubble {
  opacity: var(--tf-bubble-opacity, 0.85);
  transition: opacity var(--dur-fast, 150ms) ease;
}

/* The dial sets how loud they are at REST. Reaching for one always brings it back to
   full - otherwise a low setting would make them hard to use, not just quiet. */
.tf-bubble:hover,
.tf-bubble:focus-visible,
.tf-bubble:focus-within,
.tf-bubble-active {
  opacity: 1;
}

.tf-bubble-skin {
  background-color: var(--color-bubble);
  color: var(--color-bubble-foreground);
}
.tf-bubble-skin:hover {
  background-color: var(--color-bubble-strong);
}

/* The privacy shield being ON has to be visible at a glance. It stays the same colour
   as its neighbours - a ring says "on", so the stack still reads as one family. */
.tf-bubble-active.tf-bubble-skin {
  background-color: var(--color-bubble-strong);
  box-shadow:
    0 0 0 2px var(--color-bg-app, transparent),
    0 0 0 4px var(--color-bubble);
}

@media (prefers-reduced-motion: reduce) {
  .tf-bubble {
    transition: none;
  }
}
"""
    + CSS_END
    + "\n"
)


def comment_balance_ok(css: str) -> bool:
    """Every /* is closed by the NEXT */ and nothing outside a comment looks like prose.

    This exists because of a real failure: a comment describing Tailwind utilities wrote
    ``bg-*`` followed by ``/opacity-*``, which spells ``*/`` and closed the comment three
    lines early. Everything after it became CSS, the build died on an unexpected ``!``,
    and neither tsc nor vitest could see it - the stylesheet is only parsed by the image
    build. A stylesheet this script writes gets checked here instead.
    """
    depth = 0
    i = 0
    while i < len(css):
        if css.startswith("/*", i):
            if depth:
                return False  # a nested open means an earlier one never closed
            depth = 1
            i += 2
            continue
        if css.startswith("*/", i):
            if not depth:
                return False  # a close with nothing open: the comment ended early
            depth = 0
            i += 2
            continue
        i += 1
    return depth == 0


def section_css() -> None:
    path = ROOT / "frontend/app/globals.css"
    if not path.exists():
        skipped.append(f"[css] {path} is missing - the bubbles keep their own looks.")
        return

    if not comment_balance_ok(CSS):
        skipped.append(
            "[css] the stylesheet this script would write has an unbalanced comment, so\n"
            "  part of it would be parsed as CSS and the image build would fail. Refusing\n"
            "  to write it - fix the comment in this script."
        )
        return

    text = path.read_text()
    if CSS_START in text and CSS_END in text:
        block = text[text.index(CSS_START) : text.index(CSS_END) + len(CSS_END)]
        if block == CSS.rstrip("\n"):
            report.append("[css] already present and current - left alone")
            return
        text = text.replace(block, CSS.rstrip("\n"), 1)
        path.write_text(text)
        report.append(f"[css] {path}: the managed block was REPLACED with the current one")
        return

    # An earlier, unsentinelled version of the block. It was appended at the end of the
    # file, so everything from its header down is ours to replace - which is how a file
    # already carrying the broken comment gets repaired rather than appended to twice.
    if CSS_V1_HEADER in text:
        text = text[: text.index(CSS_V1_HEADER)].rstrip("\n") + "\n" + CSS
        path.write_text(text)
        report.append(
            f"[css] {path}: REPAIRED - the first version of this block ended its own "
            "comment early (a `*/` inside the prose), which broke the image build"
        )
        return

    path.write_text(text.rstrip("\n") + "\n" + CSS)
    report.append(f"[css] {path}: light-blue tokens + .tf-bubble / .tf-bubble-skin appended")


# ── 2. the setting ─────────────────────────────────────────────────────────────────
SPEC = f'''    "{SETTING_KEY}": SettingSpec(
        key="{SETTING_KEY}",
        type="int",
        default={DEFAULT_PCT},
        label="Floating button opacity (%)",
        description="How visible the floating corner buttons (assistant, privacy "
        "shield, announcements) are when you are not using them. They always return "
        "to full opacity on hover, so a low value quietens them without making them "
        "hard to press.",
        minimum={MIN_PCT},
        maximum={MAX_PCT},
    ),
'''

REGISTRY_OPEN = "SETTINGS_REGISTRY: dict[str, SettingSpec] = {\n"
# Prefer to land inside the general group's own banner, so the new entry sits with the
# other dashboard-facing toggles instead of above the heading that describes them.
GENERAL_BANNER_RE = re.compile(r"^ {4}# .*General \(System tab\).*\n", re.M)
CLIENT_KEYS_RE = re.compile(
    r"CLIENT_SETTING_KEYS:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((?P<inner>[^)]*)\)"
)


def section_registry() -> None:
    path = ROOT / "backend/app/core/settings_registry.py"
    if not path.exists():
        skipped.append(f"[setting] {path} is missing - no admin control was added.")
        return
    text = path.read_text()
    if SETTING_KEY in text:
        report.append("[setting] already registered - left alone")
        return

    if text.count(REGISTRY_OPEN) != 1:
        skipped.append(
            "[setting] could not find exactly one `SETTINGS_REGISTRY: dict[...] = {`.\n"
            + window(text, "SETTINGS_REGISTRY")
        )
        return

    keys = CLIENT_KEYS_RE.search(text)
    if keys is None:
        skipped.append(
            "[setting] CLIENT_SETTING_KEYS not found - a setting the frontend may not\n"
            "  read is a dial that saves and does nothing, so nothing was written."
        )
        return

    # The tuple is REBUILT rather than appended to: adding a name to the end of the
    # existing line pushes it past the 100-column limit and ruff fails the run for a
    # reason that has nothing to do with the change.
    names = [n.strip() for n in re.findall(r'"([^"]+)"', keys.group("inner"))]
    if SETTING_KEY not in names:
        names.append(SETTING_KEY)
    rebuilt = (
        "CLIENT_SETTING_KEYS: tuple[str, ...] = (\n"
        + "".join(f'    "{n}",\n' for n in names)
        + ")"
    )
    text = text[: keys.start()] + rebuilt + text[keys.end() :]

    banner = GENERAL_BANNER_RE.search(text)
    at = banner.end() if banner else text.index(REGISTRY_OPEN) + len(REGISTRY_OPEN)
    text = text[:at] + SPEC + text[at:]

    path.write_text(text)
    report.append(
        f"[setting] {path}: {SETTING_KEY} (int, {MIN_PCT}-{MAX_PCT}, default "
        f"{DEFAULT_PCT}) registered and exposed to the client"
    )


def section_client_type() -> bool:
    """The frontend's mirror of ClientSettings.

    Separate from the backend section on purpose: if the type is not widened, tsc fails
    on `data?.bubble_opacity_pct` and the whole build stops - so this is the one piece
    that cannot be left half-done and quietly degrade.
    """
    return ensure_after(
        "setting/client-type",
        ROOT / "frontend/lib/api-hooks.ts",
        "export interface ClientSettings {\n  data_freshness_threshold_hours: number;\n",
        f"  {SETTING_KEY}: number;\n",
        "ClientSettings carries the opacity",
    )


def section_backend_plumbing() -> None:
    ok = ensure_after(
        "setting/schema",
        ROOT / "backend/app/schemas/system.py",
        "    data_freshness_threshold_hours: int\n",
        f"    {SETTING_KEY}: int\n",
        "ClientSettings carries the opacity",
    )
    if not ok:
        return
    service_anchor = (
        "        data_freshness_threshold_hours=int(await get_value(db, "
        '"data_freshness_threshold_hours")),\n'
    )
    ensure_after(
        "setting/service",
        ROOT / "backend/app/services/settings_service.py",
        service_anchor,
        f'        {SETTING_KEY}=int(await get_value(db, "{SETTING_KEY}")),\n',
        "client_settings() returns it",
    )


# ── 3. publishing it to the page ───────────────────────────────────────────────────
COMPONENT = ROOT / "frontend/components/layout/bubble-theme.tsx"
COMPONENT_SRC = f'''"use client";

import {{ useEffect }} from "react";

import {{ useClientSettings }} from "@/lib/api-hooks";

/** Publishes the admin-set floating-button opacity to the page as a CSS variable.
 *
 *  The three corner buttons are styled entirely in CSS (`.tf-bubble`), so the only
 *  thing that has to travel from the database into the page is one number. Writing it
 *  to the root element rather than threading a prop through three components that share
 *  no parent means a fourth bubble picks the setting up simply by wearing the class.
 *
 *  Renders nothing. While the setting is loading, the stylesheet's own fallback applies,
 *  so the buttons are never briefly invisible - and if the request fails they stay at
 *  that fallback rather than disappearing. */
export function BubbleTheme() {{
  const {{ data }} = useClientSettings();
  const pct = data?.{SETTING_KEY};

  useEffect(() => {{
    if (pct == null) return;
    // Clamped again on the way in. The server validates the bounds, but a stale cached
    // response must not be able to make every floating control invisible.
    const clamped = Math.min({MAX_PCT}, Math.max({MIN_PCT}, pct));
    const root = document.documentElement;
    root.style.setProperty("--tf-bubble-opacity", String(clamped / 100));
    return () => {{
      root.style.removeProperty("--tf-bubble-opacity");
    }};
  }}, [pct]);

  return null;
}}
'''

PROVIDERS_IMPORT_ANCHOR = (
    'import { SessionCacheGuard } from "@/components/layout/session-cache-guard";'
)
PROVIDERS_MOUNT_ANCHOR = "<SessionCacheGuard>{children}</SessionCacheGuard>"
PROVIDERS_MOUNT_NEW = """<SessionCacheGuard>
            {/* Renders nothing: it only publishes the admin-set bubble opacity as a
                CSS variable. Mounted here so every route gets it, inside AuthProvider
                because the setting is read through an authenticated request. */}
            <BubbleTheme />
            {children}
          </SessionCacheGuard>"""


def section_publisher() -> None:
    providers = ROOT / "frontend/app/providers.tsx"
    if not providers.exists():
        skipped.append(
            f"[opacity] {providers} is missing - the CSS fallback applies and the admin\n"
            "  dial will have no effect. No component was written."
        )
        return
    text = providers.read_text()
    if "BubbleTheme" in text:
        report.append("[opacity] already mounted - left alone")
        COMPONENT.parent.mkdir(parents=True, exist_ok=True)
        COMPONENT.write_text(COMPONENT_SRC)
        return
    if text.count(PROVIDERS_MOUNT_ANCHOR) != 1 or text.count(PROVIDERS_IMPORT_ANCHOR) != 1:
        skipped.append(
            f"[opacity] {providers} does not look the way this expects, so nothing was\n"
            "  mounted and no component file was written - an unmounted component is\n"
            "  just a file nobody runs. The CSS fallback applies; the admin dial will\n"
            "  save but not take effect. On disk:\n" + window(text, "SessionCacheGuard")
        )
        return

    COMPONENT.parent.mkdir(parents=True, exist_ok=True)
    COMPONENT.write_text(COMPONENT_SRC)
    # Imports are path-sorted in this file; bubble-theme precedes session-cache-guard.
    text = text.replace(
        PROVIDERS_IMPORT_ANCHOR,
        'import { BubbleTheme } from "@/components/layout/bubble-theme";\n'
        + PROVIDERS_IMPORT_ANCHOR,
        1,
    )
    text = text.replace(PROVIDERS_MOUNT_ANCHOR, PROVIDERS_MOUNT_NEW, 1)
    providers.write_text(text)
    report.append(f"[opacity] {COMPONENT} written and mounted in {providers}")


# ── 4. the three buttons ───────────────────────────────────────────────────────────
def section_buttons() -> None:
    apply_swaps(
        "bubble/privacy-shield",
        ROOT / "frontend/components/effects/privacy-shield.tsx",
        already="tf-bubble",
        swaps=[
            Swap(
                '"fixed right-4 z-[60] hidden h-11 w-11 items-center justify-center rounded-full shadow-lg [@media(hover:hover)]:flex",',
                '"tf-bubble tf-bubble-skin fixed right-4 z-[60] hidden h-11 w-11 items-center justify-center rounded-full shadow-lg [@media(hover:hover)]:flex",',
                why="wears the shared skin + opacity",
            ),
            Swap(
                "          // Dimmed at rest: these float over page content (table pagination sits\n"
                "          // right underneath) and a solid button there hides data. Full opacity\n"
                "          // returns on hover/focus, and while the shield is ON it stays visible so\n"
                "          // its state is never in doubt.\n"
                '          "opacity-40 transition-all duration-[var(--dur-fast)] hover:scale-105 hover:opacity-100 focus-visible:opacity-100 active:scale-95",',
                "          // How loud it is at rest is now one admin setting shared by all three\n"
                "          // corner buttons (.tf-bubble), not a number hard-coded here: they float\n"
                "          // over page content, and how much that matters depends on the screen.\n"
                "          // Hover and focus still bring it back to full - see globals.css.\n"
                '          "transition-all duration-[var(--dur-fast)] hover:scale-105 active:scale-95",',
                required=False,
                why="its own dimming handed to the shared dial",
            ),
            Swap(
                "          on\n"
                '            ? "opacity-100 bg-[color:var(--color-accent)] text-[color:var(--color-accent-foreground)]"\n'
                '            : "bg-[color:var(--color-bg-elevated)] text-muted-foreground hover:text-foreground",',
                "          // ON has to be visible at a glance, but it is still the same bubble: a\n"
                "          // ring says so, rather than a colour that breaks the set of three.\n"
                '          on && "tf-bubble-active",',
                required=False,
                why="ON state kept visible as a ring",
            ),
        ],
    )

    apply_swaps(
        "bubble/announcement",
        ROOT / "frontend/components/layout/announcement-bar.tsx",
        already="tf-bubble",
        swaps=[
            Swap(
                'className="fixed right-4 z-[60] opacity-40 transition-opacity hover:opacity-100 focus-within:opacity-100"',
                'className="tf-bubble fixed right-4 z-[60]"',
                why="opacity comes from the dial",
            ),
            Swap(
                'className="relative h-11 w-11 rounded-full shadow-lg transition-transform hover:scale-105 active:scale-95"',
                'className="tf-bubble-skin relative h-11 w-11 rounded-full shadow-lg transition-transform hover:scale-105 active:scale-95"',
                why="wears the shared skin",
            ),
            Swap(
                'className="absolute inset-0 animate-ping rounded-full bg-[color:var(--color-accent)] opacity-20"',
                'className="absolute inset-0 animate-ping rounded-full bg-[color:var(--color-bubble)] opacity-20"',
                required=False,
                why="its ping halo matches the new colour",
            ),
        ],
    )

    apply_swaps(
        "bubble/assistant",
        ROOT / "frontend/components/chat/chat-widget.tsx",
        already="tf-bubble",
        swaps=[
            Swap(
                'className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition hover:scale-105"',
                'className="tf-bubble tf-bubble-skin flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition hover:scale-105"',
                why="wears the shared skin + opacity",
            )
        ],
    )


def main() -> int:
    if not (ROOT / "frontend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    section_css()
    section_registry()
    section_backend_plumbing()
    # The publisher READS ClientSettings.bubble_opacity_pct. If the type was not
    # widened, mounting a component that reads a field TypeScript does not know about
    # fails the build - and a failed build helps nobody. The CSS fallback still applies,
    # so the bubbles look right; only the admin dial is inert, and it says so.
    if section_client_type():
        section_publisher()
    else:
        skipped.append(
            "[opacity] the frontend's ClientSettings type was not widened, so no\n"
            "  component was written or mounted - it would not compile. The bubbles\n"
            "  still get their new look from the stylesheet's fallback opacity; the\n"
            "  admin dial saves but has no effect until this is applied."
        )
    section_buttons()

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    if skipped:
        print("\nSKIPPED (nothing written for these):")
        for entry in skipped:
            print(f"\n  {entry}")
    print(
        "\nWhere the dial lives: Admin -> System -> 'Floating button opacity (%)'."
        f"\nRange {MIN_PCT}-{MAX_PCT}, default {DEFAULT_PCT}. Hovering a bubble always"
        " shows it at full."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

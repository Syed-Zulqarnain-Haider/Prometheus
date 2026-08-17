#!/usr/bin/env python3
"""Generate the PWA icon set for the installed app.

Chrome will not offer "Install app" without a 192px AND a 512px icon in the manifest,
and iOS ignores the manifest entirely - it needs its own apple-touch-icon link. So four
files, drawn here rather than hand-exported so the set can be regenerated from one
definition if the mark ever changes.

  icon-192.png            manifest, minimum for installability
  icon-512.png            manifest, used for the splash screen
  icon-maskable-512.png   manifest, purpose="maskable": Android crops icons to the
                          launcher's shape (circle, squircle, rounded square), so the
                          mark is drawn inside the centre 60% safe zone with the
                          background bled to the edges. Without this the flame gets its
                          tips clipped off on most Android launchers.
  apple-touch-icon.png    180px, iOS home screen. NO transparency and no rounded corners
                          drawn in - iOS applies its own mask and a pre-rounded icon
                          ends up double-rounded.

The mark is a flame, drawn as a filled outline rather than set in a typeface, so there
is no font dependency at build time.

Idempotent: rerunning overwrites the same four files. Output is committed, so the server
never needs Pillow.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - developer machine only
    print("ABORTED: Pillow is required (pip install Pillow)", file=sys.stderr)
    raise SystemExit(1)

OUT = Path("frontend/public")

BG_TOP = (22, 22, 28)
BG_BOTTOM = (10, 10, 12)
FLAME_OUTER = (255, 106, 0)
FLAME_INNER = (255, 199, 92)

# Supersampling factor: everything is drawn large and downscaled, which is what gives the
# curves clean edges - PIL has no antialiased polygon fill.
SS = 4


def flame_points(cx: float, cy_top: float, height: float, width: float) -> list[tuple[float, float]]:
    """Outline of a flame: a leaning, curling tongue over a round belly.

    ``t`` runs 0 (tip) to 1 (base). Three things separate a flame from a teardrop, and
    all three are needed - drop any one and it reads as water:

      * the axis LEANS, tip offset sideways and settling back over the belly;
      * the sides are ASYMMETRIC, the outer edge fuller than the inner, which is what
        makes the tip read as curling rather than merely pointing;
      * the widening is fast then flat, so there is a waist rather than a straight taper.
    """
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    steps = 200
    for i in range(steps + 1):
        t = i / steps
        # Axis: tip pushed right, returning to centre by the belly.
        axis = cx + width * 1.15 * (1 - t) ** 1.7
        half = width * math.sin(math.pi / 2 * t) ** 0.62
        half *= 1 - 0.16 * math.sin(math.pi * t) ** 2  # waist
        wave = math.sin(math.pi * t)
        y = cy_top + height * t
        left.append((axis - half * (1 + 0.34 * wave), y))
        right.append((axis + half * (1 - 0.20 * wave), y))
    return left + list(reversed(right))


def draw_flame(draw: ImageDraw.ImageDraw, cx: float, cy_top: float, height: float, width: float, colour: tuple[int, int, int]) -> None:
    # Belly first: a circle wider than the tongue, so the flame sits on a round base
    # instead of ending in the flat line the outline would otherwise leave.
    base_y = cy_top + height
    belly = width * 1.16
    draw.ellipse(
        [cx - belly, base_y - belly * 1.30, cx + belly, base_y + belly * 0.62],
        fill=colour,
    )
    draw.polygon(flame_points(cx, cy_top, height, width), fill=colour)


def render(size: int, mark_scale: float, rounded: bool) -> Image.Image:
    big = size * SS
    image = Image.new("RGB", (big, big), BG_BOTTOM)
    draw = ImageDraw.Draw(image)

    # Vertical gradient, one line at a time - cheap and exact at this size.
    for y in range(big):
        blend = y / max(big - 1, 1)
        draw.line(
            [(0, y), (big, y)],
            fill=tuple(
                round(BG_TOP[c] + (BG_BOTTOM[c] - BG_TOP[c]) * blend) for c in range(3)
            ),
        )

    height = big * 0.56 * mark_scale
    width = big * 0.20 * mark_scale
    # The tongue leans right, so the mark's visual centre sits right of its axis; pull the
    # axis back to compensate, otherwise the icon looks glued to the right edge.
    cx = big / 2 - width * 0.34
    top = (big - height) / 2 - big * 0.04 * mark_scale
    draw_flame(draw, cx, top, height, width, FLAME_OUTER)
    # Inner flame: the same shape smaller and lower, for the hot core. Nudged right so it
    # stays inside the outer belly rather than breaking its left edge.
    draw_flame(
        draw,
        cx + width * 0.16,
        top + height * 0.44,
        height * 0.52,
        width * 0.48,
        FLAME_INNER,
    )

    image = image.resize((size, size), Image.LANCZOS)

    if rounded:
        # A rounded-square mask for the plain (non-maskable) icons, so the tile does not
        # look like a bare screenshot on surfaces that do not mask it themselves.
        mask = Image.new("L", (size * SS, size * SS), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size * SS - 1, size * SS - 1], radius=int(size * SS * 0.22), fill=255
        )
        mask = mask.resize((size, size), Image.LANCZOS)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(image, (0, 0), mask)
        return out
    return image


def main() -> None:
    if not OUT.is_dir():
        print(f"ABORTED: {OUT} not found - run from the repository root", file=sys.stderr)
        raise SystemExit(1)

    written = []
    for name, size, scale, rounded in (
        ("icon-192.png", 192, 1.0, True),
        ("icon-512.png", 512, 1.0, True),
        # Maskable: mark shrunk into the centre safe zone, background square to the edge.
        ("icon-maskable-512.png", 512, 0.62, False),
        # iOS masks it itself, so square and opaque.
        ("apple-touch-icon.png", 180, 1.0, False),
    ):
        image = render(size, scale, rounded)
        path = OUT / name
        image.save(path, "PNG", optimize=True)
        written.append(f"{name} ({size}x{size})")

    print("wrote:")
    for line in written:
        print(f"  {OUT}/{line}")


if __name__ == "__main__":
    main()

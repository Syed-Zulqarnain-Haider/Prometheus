# Brand palette - measured from the reference video

Not eyeballed. Eight frames were extracted across the 57s reference clip and quantised with
PIL; every value below is a colour that actually occupies a measurable share of a frame.
Source frames: 2s, 8s, 15s, 22s, 30s, 38s, 46s, 54s.

## What the reference actually does

It is a **near-black canvas with deep-green surfaces and one mint accent**, punctuated by
**full-light sections** (the blog band) that invert to near-white with near-black text. It is
not a "dark theme" - it is a dark canvas that switches to light for editorial sections. Both
halves have to exist in the token set.

## Measured values

### Dark canvas (frames 2, 8, 15, 30, 54)

| Role | Hex | Evidence |
| --- | --- | --- |
| Page black (outermost) | `#010101` | 17.5% of f15 |
| Canvas | `#0a0a0a` - `#0e0e0e` | 11.5% f2, 18.2% f30 |
| Surface / card | `#171717` - `#181818` | the single most common colour, 15-36% in every dark frame |
| Surface raised | `#1a1a1a` - `#1e2120` | 9.6% f30, 15.3% f30 |

### Green surfaces (the brand's body)

| Role | Hex | Evidence |
| --- | --- | --- |
| Green surface, deepest | `#0b1816` | 13.8% of f22 |
| Green surface | `#1a3732` | 10.6% of f22 |
| Green surface, muted | `#25302d` / `#293631` | 24.3% f46, 19.8% f8 |
| Green surface, lifted | `#2d403e` / `#3a5752` | 12.6% f15, 16.4% f22 |

### Accent (the mint CTA band, f54)

| Role | Hex | Evidence |
| --- | --- | --- |
| **Accent / brand** | `#8fbcaf` | 23.7% of f54 - the large mint CTA panel |
| Accent, deep (on light) | `#3a5752` | 16.4% of f22 |

### Light sections (frames 22, 38, 46)

| Role | Hex | Evidence |
| --- | --- | --- |
| Light canvas | `#fcfcfc` | 32-62% of f22/f38/f46 |
| Light surface | `#f9f9f9` | 22.2% of f46 |
| Light border | `#e4e6e6` | 8.4% of f46 |
| Text on dark, muted | `#bcc4c2` / `#bdc7c6` | 4.7% f38, 6.6% f22 |
| Text on light | `#121313` | 19.4% of f38 |

## Form language (from the frames, not invented)

- **Pills everywhere**: nav items, badges ("Daily Finances", "Our Benefits", "Our Blog"),
  and buttons are fully rounded (`rounded-full`), not the 6px radius the dashboard uses now.
- **Large soft cards**: content blocks are heavily rounded (~24px) with no visible border on
  dark - separation comes from the surface step, not a stroke.
- **Radial green glow** bleeding from the edges of the black surround.
- **Halftone/dot-matrix data motifs** used as decoration behind hero and feature blocks.
- **Type**: very large, tight-tracking display headings; small, muted body copy.

## Mapping to the dashboard

The dashboard already themes through CSS custom properties, so this lands as a token swap
rather than a component rewrite. The theme selector stays: the dark theme takes the black +
green canvas, and the light theme takes the `#fcfcfc` surfaces with `#3a5752` as the accent
(the mint `#8fbcaf` fails contrast on white for text, so on light it is a fill, not a
foreground).

Charts follow the same palette, with the mint as series 1 - but chart series need distinct
hues to stay readable, so the categorical ramp extends beyond the brand greens rather than
shipping five shades of the same colour.

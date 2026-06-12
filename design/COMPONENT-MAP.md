# Terafort — CEO Command Center · Component & Token Map

A handoff reference for **Claude Code** (and for rebuilding this screen as a
Figma file). Everything visual is driven by design tokens in
`styles/tokens.css`; every block of markup carries a `data-component` hook so
components are 1:1 addressable.

---

## 1. File map

| File | Role |
|------|------|
| `CEO Command Center.html` | The screen. All **text/values live here** as static markup (directly editable). |
| `styles/tokens.css` | **Design tokens** — colors, type, spacing, radius, shadow, motion. Single source of truth → map each `--var` to a Figma variable/style. |
| `styles/dashboard.css` | Component styles. References tokens only; no hard-coded values. |
| `styles/polish.css` | **Aesthetic layer** (loaded last): atmospheric glow canvas + grain, display/mono type roles, LIVE pill, card depth + hover lift, nav glow, entrance motion. |
| `scripts/anim.js` | Entrance stagger + number count-up (progressive enhancement; resting state always visible). |
| `scripts/data.js` | `window.DASH` — **chart series + placeholder data**. Swap with live data here. |
| `scripts/charts.js` | Hand-rolled SVG renderers (no chart lib): `sparkline`, `donut`, `barTarget`, `combo`. |
| `scripts/icons.js` | Stroke icon set (`window.icon(name, size)`), 24×24 viewBox, `currentColor`. |
| `scripts/render.js` | Mounts charts into `[data-chart]` / `[data-spark]` / `[data-donut]` slots + interactivity. |
| `scripts/charts-ext.js` | Extra SVG renderers for secondary pages: `line`, `bars`, `hbars`, `donutSegments`. |
| `scripts/pages-core.js` | Page builders + shared helpers: **Finance, UA, Products, Product Factory**. |
| `scripts/pages-more.js` | Page builders: **User Analytics, AI & Operations, Executive, Reports, Alerts**. |
| `scripts/router.js` | Client-side router — nav swaps pages into `#page-dynamic`, updates topbar, persists in hash + localStorage. |
| `scripts/interactive.js` | **Sortable tables** (click any header) + **clickable chart legends** (toggle series). Re-runs for router pages. |
| `scripts/tweaks.jsx` | Polish-variation panel (accent / surface / corners / density) — each variation = a token rewrite. |

---

## 2. Token → Figma crosswalk

Create these as Figma **variables** (Color / Number) and **text styles**. Names
below match the CSS custom properties exactly.

### Color · Surfaces
| Token | Value | Use |
|-------|-------|-----|
| `--color-bg-app` | `#080b11` | Page canvas |
| `--color-bg-sidebar` | `#0b0f16` | Left rail |
| `--color-bg-card` | `#11161f` | Card surface |
| `--color-bg-card-sunken` | `#0d121a` | Chart plot wells |
| `--color-bg-elevated` | `#171e29` | Hover rows, chips, track |

### Color · Strokes
| `--color-border` `#1c2430` · `--color-border-strong` `#28323f` · `--color-border-faint` `#151b24` |

### Color · Text
| `--color-text-primary` `#eaf0f7` · `--color-text-secondary` `#97a3b2` · `--color-text-muted` `#5d6877` |

### Color · Accents / Semantic
| Token | Value | Meaning |
|-------|-------|---------|
| `--color-accent` | `#4187f5` | Primary azure — links, active nav, bars, donut |
| `--color-brand` | `#24cfbe` | Terafort teal (logo / glows) |
| `--color-positive` | `#2bc07d` | Jade — up / good (deltas, SCALE) |
| `--color-negative` | `#f05b62` | Coral — down / bad |
| `--color-purple` | `#9168e8` | Violet — cash, installs, PROTOTYPE |
| `--color-amber` | `#e8a93c` | Gold — IMPROVE |
| `--color-orange` | `#ee7d49` | Ember — REVIEW / attention |

The palette is built on color theory: a cool blue-black neutral foundation (single ~228° hue bias, never pure gray), a refined **azure** primary, the on-brand **teal** as analogous support, and a harmonious categorical ramp (azure → teal → violet → gold → coral) tuned to a common lightness/chroma so hues never clash. `*-soft` variants are the translucent badge/chip backgrounds.

### Typography (family: **Manrope**, tabular figures on numerics)
| Token | Size | Used by |
|-------|------|---------|
| `--fs-display` | 28px* | Page title (`.topbar__title`, fluid via `clamp`) |
| `--fs-kpi` | 27px | KPI value |
| `--fs-stat` | 22px | Key-ratio value |
| `--fs-stat-sm` | 18px | Compact stat value |
| `--fs-body` | 13px | Table / list |
| `--fs-label` | 11px | Uppercase labels (tracking `--ls-label` 0.07em) |
| `--fs-micro` | 10px | Badges, axis ticks |

Weights: `--fw-regular 400 / medium 500 / semibold 600 / bold 700 / extra 800`.

### Spacing (4-pt base) · Radius · Elevation
`--space-1..8` = 4/8/12/16/20/24/32. `--card-pad` 18px · `--grid-gap` 14px ·
`--sidebar-width` 248px. Radius `--radius-card 12 / inner 8 / chip 6 / pill 999`.
Shadow `--shadow-card`, `--shadow-pop`.

---

## 3. Component inventory

Each is tagged with `data-component="…"` in the markup.

| Component | Selector | Notes / variants |
|-----------|----------|------------------|
| **Sidebar** | `.sidebar` | brand block, `.nav`, `.year-target`, footer |
| **Nav item** | `.nav__item` | states: default · `:hover` · `.is-active` (blue rail + tint) · `.is-header` |
| **Year-target card** | `.year-target` | label / value / sub / achieved + `.progress` |
| **Topbar** | `.topbar` | title + subtitle + `.control` buttons |
| **Control button** | `.control` | `.control--muted` for the compare dropdown |
| **KPI card** | `.kpi` (a `.card`) | label · value · `.delta` · `.kpi__spark` (sparkline slot) |
| **Delta chip** | `.delta` | `.delta--up` (green ▲) / `.delta--down` (red ▼) + `.delta__note` |
| **Card** | `.card` | primitive. `.card__head` + `.card__title` (`em` = dim suffix) |
| **Donut / progress** | `.donut[data-donut]` | value ring; center overlay `.donut__pct` |
| **Stat list** | `.stat-list` | label/value pairs |
| **Bar+target chart** | `[data-chart="monthly-trend"]` | blue bars (future bars dimmed) + dashed target line + hover tip |
| **Key-ratios grid** | `.ratio-grid` | 3-col `.ratio` tiles |
| **Product table** | `.ptable` | rows hover-highlight; `.product-icon`, `.cat--{game,health,finance,lifestyle}`, `.badge--{scale,improve,review,prototype}` |
| **UA performance** | `[data-chart="ua"]` | 4 metric tiles + combo chart (gradient bars + yellow CPI line, dual axis) |
| **Stat tiles** | `.tile-grid` | 4-col `.tile` (product health) |
| **Pipeline** | `.pipeline` | `.pipe-step` × 5 with arrows; `.pipe-step--killed` is red |
| **Success rate** | `.success-rate` | `.progress` fill animates to value |
| **Alerts** | `.alerts` | `.alert` rows, `.alert__dot--{positive,info,warn}` |
| **Card link** | `.card-link` | "View all →" |
| **Tooltip** | `.chart-tip` | shared floating hover tip for charts |

---

## 4. Charts (how they scale)

Every chart is SVG with a fixed `viewBox` + `preserveAspectRatio="none"` and
`vector-effect:non-scaling-stroke` on strokes → it stretches to container width
at a fixed CSS height while lines stay crisp. Colors are read from CSS tokens at
render time, so re-theming (or a Tweak) just needs `window.__rerenderCharts()`.

To rebuild as Figma vectors: bars = rects on a baseline; target/CPI = polylines;
donut = a ring with `stroke-dasharray` = `(pct/100) × circumference`.

---

## 5. Interactivity
- **Nav** — click sets `.is-active` (single-select).
- **Date range** — the `[data-date-range]` button cycles preset ranges (label + compare).
- **Chart hover** — bars show a tooltip with the series value.
- **Tweaks panel** — toggled from the toolbar; rewrites tokens on `:root`. Variants: Accent (Blue/Teal/Violet) · Surface (Bordered/Elevated/Flat) · Corners (Sharp/Default/Rounded) · Density (Comfortable/Compact).

---

## 6. Theme toggle (light / dark)
The topbar **`[data-theme-toggle]`** button flips the whole UI. Mechanism: it
sets `data-theme="light"` on `<html>`; `tokens.css` has a single
`:root[data-theme="light"] { … }` block that overrides only the surface/text/
stroke/chart tokens. Components are untouched — they read the same `--vars`.
The choice persists in `localStorage` (`tf-theme`) and charts re-render to pick
up the new token colors. In Figma this maps to a **second variable mode**
("Light") on the same color variables.

## 7. Navigation & pages (all nav items work)
Every sidebar item routes to a real page. **Overview** is the static markup in
`CEO Command Center.html` (`#page-overview`); the other nine are built by
functions in `window.PAGES` (`pages-core.js` + `pages-more.js`) and rendered
into `#page-dynamic` by `router.js`:

| Nav item | `data-page-key` | Page contents |
|----------|-----------------|---------------|
| Overview | `overview` | KPI cards, donut, trend, ratios, portfolio, UA, health, factory, alerts |
| Finance | `finance` | P&L, cash-flow line, revenue mix donut, opex breakdown |
| UA Marketing | `ua` | Spend/install/CPI combo, channel mix donut, channel table |
| Products | `products` | Per-product cards with sparklines + status badges |
| Product Factory | `factory` | Pipeline funnel, greenlit / killed lists |
| User Analytics | `analytics` | Retention curve, DAU line, retention tiles, platform mix |
| AI & Operations | `ai` | AI workload bars, spend mix, ops status, automation bars |
| Executive | `executive` | Company OKRs, revenue-vs-target, board stats |
| Reports | `reports` | Report library table with status pills |
| Alerts | `alerts` | Alerts grouped by severity |

Each page reuses the same component classes (`.card`, `.kpi`, `.ptable`,
`.badge`, charts), so they map to the **same Figma components** with different
content. The current page is kept in `location.hash` + `localStorage` (`tf-page`)
so a refresh restores it. New page = add a `window.PAGES.<key>` builder and a
nav item with `data-page-key="<key>"`.

## 8. Adding more content

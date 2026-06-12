# DESIGN.md — Overview screen: widgets → real metrics, targets, and demo data

This maps the owner's **CEO Command Center** Overview design (`design/`) onto our
real API, and records the owner's locked decisions. The visual source of truth is
`design/tokens.css` (the **"Swiss Ledger"** theme — warm dark *night ledger* +
light *paper*). Those tokens are ported into the frontend (`app/theme.css`) so every
component and the ECharts theme consume the exact same variables.

> Note: `design/COMPONENT-MAP.md` §2 lists an older blue palette — it is **stale**.
> `tokens.css` (oxblood / warm neutrals) wins.

---

## 1. REAL DATA widgets (wired to the live API)

| Widget (design) | Real source | Field(s) |
|---|---|---|
| **KPI — Revenue** | `/metrics/summary` | `current.total_revenue_usd` (net revenue = IAP net + ad, by contract) |
| **KPI — Spend** | `/metrics/summary` | `current.total_ua_spend_usd` |
| **KPI — Net** | `/metrics/summary` | `current.total_iap_net_usd` + `current.total_ad_revenue_usd` (= `total_revenue_usd`). See note ‡ |
| **KPI — Profit** | `/metrics/summary` | `current.profit_usd` |
| **KPI — Profit %** | `/metrics/summary` | `current.profit_margin` (period ratio = profit / revenue) |
| **KPI deltas (▲▼)** | `/metrics/summary?compare=1` | each KPI's `current` vs `previous` value |
| **KPI sparklines** | `/metrics/timeseries` | `series[].<metric>` over the selected range (bucket = day) |
| **Monthly trend (bars)** | `/metrics/timeseries` | `bucket=month`, metric `total_revenue_usd` (target line → §2) |
| **Key ratios — ROAS** | `/metrics/summary` | `current.roas` (recomputed from totals; never a daily average) |
| **Key ratios — Ad ROAS** | `/metrics/summary` | `current.ad_roas` |
| **Key ratios — CPI** | `/metrics/summary` | `current.cpi` |
| **Portfolio / apps table** | `/metrics/table` | one row per app, sorted by `total_revenue_usd`; columns gated by the caller's permitted metric groups |
| **Date + comparison picker** | global filter bar | `date_from`/`date_to`/`compare` (URL-synced — already built) |
| **Data-as-of banner** | `/meta/freshness` | `bq_built_at`, `last_status` (already built) |

‡ **"Net" is ambiguous in the design.** Our `total_revenue_usd` is *already net* of
store/platform fees (`= total_iap_net_usd + total_ad_revenue_usd`, contract rule 4),
so "Revenue" and "Net Revenue" are the same number. To give five *distinct* KPIs we
show **Gross Revenue** (`total_iap_gross_usd + total_ad_revenue_usd`, both real
additive fields summed client-side) as "Revenue" and **Net Revenue**
(`total_revenue_usd`) as "Net". If the owner prefers a different split, only this row
changes.

All "real" KPI/ratio math comes pre-aggregated from the API (period ratios are
recomputed from summed totals server-side — Step 3.2). The client never averages
daily ratios.

---

## 2. ADMIN-SET TARGETS (approved feature — build with Step 7)

The **revenue-progress donut** ("35.6% to yearly target") shows **real** progress:
actual revenue (from the API) ÷ an **admin-set target**. Targets are data, not code.

**Backend (lands in Step 7 admin work):**
- New table `revenue_targets`:
  - `id` PK, `year` SMALLINT NOT NULL, `month` SMALLINT NULL (NULL = yearly target),
    `target_usd` NUMERIC(18,4) NOT NULL, `set_by` UUID → users, `updated_at` TIMESTAMPTZ.
  - UNIQUE `(year, month)`. Added via the metric-registry-independent Alembic migration
    (it's a settings table, not a fact column).
  - DB grants: `api_service` SELECT + UPSERT; admin-only at the API layer.
- Endpoints:
  - `GET /api/v1/meta/targets?year=YYYY` → `{ yearly, months: [{month, target_usd}] }`
    (auth required; read-only; safe for all roles to read).
  - `PUT /api/v1/admin/targets` (capability `admin_panel`) → upsert a target; audited
    (`admin_action` = `set_revenue_target`).
- Progress = `SUM(total_revenue_usd)` for the target's period (YTD for yearly) from the
  scoped summary, ÷ `target_usd`. Donut renders the real percentage; no target set →
  the donut shows an "unset" empty state (never a fake number).

**Frontend now (Step 5 wires it):** the donut component is real-data; until the
endpoint exists it shows the "target not set" empty state. It is **not** a demo widget.

---

## 3. DEMO DATA widgets (owner decision — visual completeness only)

These have **no real source yet**. Per the owner, they ship for visual completeness
under strict rules so they can never be mistaken for real numbers.

**Rules (enforced):**
1. Every demo widget renders **only** from `lib/demo-data.ts` (the single, clearly
   named demo module). No demo values live inside components.
2. Every demo widget shows a visible **`DEMO DATA`** badge (`components/ui/demo-badge.tsx`).
3. All demo widgets are gated by **one flag**: `NEXT_PUBLIC_SHOW_DEMO_WIDGETS`
   (`lib/demo-mode.ts` → `SHOW_DEMO_WIDGETS`). Off → the widgets do not render at all.

| Demo widget | What it shows | Real source that could replace it later |
|---|---|---|
| **Cash / Runway** | cash balance + months of runway | Finance system / accounting export (e.g. Brex, NetSuite) |
| **LTV** | lifetime value per user/cohort | Predictive LTV model over IAP + ad ARPDAU |
| **Cohort ROAS D30 / D90** | payback curve by cohort age | Cohort revenue tables (Adjust/Singular) joined to spend |
| **Payback period** | days to recoup CAC | Same cohort pipeline as cohort ROAS |
| **DAU / MAU** | active users + stickiness | Product analytics events (e.g. Firebase/BigQuery events) |
| **Retention** | D1/D7/D30 retention curve | Cohort retention tables from the events pipeline |
| **Ratings** | app store rating + reviews | App Store Connect API + Google Play Developer API |
| **Product Factory** | build pipeline funnel | Internal PM tool (Linear/Jira) status export |
| **Alerts** | anomaly / threshold alerts | Monitoring + anomaly detection over the fact table |

Demo widgets are **Overview-only** visual filler (Step 5). This document is the
register of which widgets are demo vs real.

---

## 4. Theme tokens (ported)

`design/tokens.css` is mirrored into `frontend/app/theme.css` **verbatim** (both
modes): `:root` = dark *night ledger*; `:root[data-theme="light"]` = *paper*. The
theme is switched by `next-themes` via the `data-theme` attribute. Components consume
the `--color-*` tokens through Tailwind; the ECharts theme reads the `--chart-*` and
`--color-*` tokens at render time (`lib/echarts-theme.ts`), so re-theming and
dark/light switching are a single source of truth.

Fonts: **Archivo** (body) + **Spectral** (serif display/KPI) per the tokens, loaded
from Google Fonts; system serif/sans fallbacks are in the token values so the UI
degrades gracefully if the webfont is unavailable.

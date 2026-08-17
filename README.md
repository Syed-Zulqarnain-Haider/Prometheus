# Prometheus - Performance Dashboard

An enterprise analytics dashboard for mobile-app performance data, replacing a Looker
Studio dashboard for ~50 internal users. It turns the daily BigQuery performance feed into
a fast, role-aware web app: revenue, UA spend, installs, ad/IAP breakdowns, ROAS/CPI, and
profitability - with per-user row-level access control and a customizable Executive
Overview.

> **Project memory & locked decisions:** see [`CLAUDE.md`](./CLAUDE.md).
> **Change history:** [`CHANGELOG.md`](./CHANGELOG.md) - what changed, when, and why.
> **Local run (step-by-step):** [`docs/RUNBOOK-LOCAL.md`](./docs/RUNBOOK-LOCAL.md) ·
> **Production deploy:** [`docs/DEPLOY.md`](./docs/DEPLOY.md) ·
> **Design system:** [`docs/DESIGN.md`](./docs/DESIGN.md).

---

## 1. What it is

- **Audience:** ~50 internal users across roles (executives, pod owners, marketing,
  finance, analysts/viewers).
- **Purpose:** a single, governed analytics surface for mobile-app performance - the
  "Executive Overview" plus Revenue, UA, Store, Apps Explorer, and App Detail pages.
- **Why not Looker:** server-side RBAC down to the row, a faster purpose-built UI,
  saved views/reports with admin-approved sharing, exports, and an auditable trail.

---

## 2. Architecture

A **layered modular monolith** per tier (no microservices at this scale), cleanly split
backend ↔ frontend and serving ↔ analytics.

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 14 (App Router, TypeScript strict), Tailwind + shadcn/ui, Apache ECharts (tree-shaken, **lazy-loaded**), TanStack Table/Virtual/Query - deployed on **Vercel** |
| **Backend** | FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.0 async + Alembic - deployed on **Cloud Run** |
| **Serving DB** | **Neon** Postgres (serverless, **pooled**, TLS over the public internet) |
| **Cache** | **Upstash** Redis (serverless, TLS `rediss://`) - key prefix `agg:*`, busted by the daily sync |
| **Auth** | **Firebase Auth**; ID tokens verified server-side (`firebase-admin`) on every route |
| **Assistant** | Optional **ask-your-data** chatbot - Claude / ChatGPT / Gemini / Grok, whichever provider keys are set (see §3) |
| **Source** | **BigQuery** - the admin-set `bq_view` setting: a view **or** the raw `unified_daily_performance` table (the sync computes derived metrics itself, so a table works directly) |

### Data flow

```
BigQuery source (the admin-set bq_view: a view OR unified_daily_performance)
        │   daily sync: validate → staged load → integrity checks → UPSERT (history accumulates)
        ▼
Neon Postgres  (fact_daily_performance, dim_app, RBAC, audit, saved views/reports, layouts…)
        │   FastAPI (Cloud Run): RBAC + scoped SQL, results cached in Upstash Redis (agg:*)
        ▼
Next.js UI (Vercel)  ◄── Firebase ID token on every request
```

The API **never** queries BigQuery; users only ever read the materialized Postgres tables.

---

## 3. Key concepts

### Metric registry - single source of truth
`backend/app/core/metric_registry.py` (mirrored by `sync/metric_registry.py`) defines
**every fact column** (the curated registry - grown to include the reported `rpt_*` finance
ladder) and their metric groups. Generated from it: the Postgres fact DDL,
the per-role Pydantic response models, the RBAC column filters, and the fact indexes
(including the date covering index). A **drift guard** test
(`tests/test_metric_registry_parity.py`) fails CI if the two copies ever diverge in
columns/types/groups/order. **Never hand-write column lists elsewhere.** The curated
registry is still authoritative; columns an admin adopts from BigQuery at runtime (see
**Schema reconcile**) are carried alongside it as an `unclassified`, admin-only group.

### RBAC - enforced server-side
- **Roles:** `admin`, `executive`, `pod_owner`, `marketing`, `finance`, `viewer`.
- **Row scope:** `user_scopes(scope_type ∈ all|hou|pod|publisher|app, scope_value)`;
  effective access is the UNION of a user's rows. The scope is compiled to a SQL `WHERE`
  predicate and injected **first** in every query; client filters can only **narrow** it,
  never widen it (no-scope ⇒ no rows, fail-closed).
- **Metric scope:** `role_metric_permissions` (groups: store_installs, ua_spend,
  ad_revenue, iap_revenue, attribution, profitability - plus `unclassified`, granted to
  admins only for BigQuery-discovered columns) → forbidden columns are never serialized
  (per-role models from the registry).
- **Defense in depth:** the aggregate cache key varies by scope **and** permitted groups,
  so cached payloads never cross permission profiles; out-of-scope resources return **404**
  (indistinguishable from nonexistent). Frontend hiding is cosmetic only.
- **Granting a scope** (`components/admin/scope-editor.tsx`): the type is a dropdown and the
  value is a **searchable picker** fed from `/apps` - the dimension table, so a pod or
  publisher with no rows in the current date window still appears. Apps list by name with
  the canonical key on hover. It stays typeable, because a grant may legitimately name a pod
  that has no apps mapped yet; a value the list doesn't contain is offered explicitly rather
  than dropped. Changing the type clears the value - a pod name is not a publisher name, and
  carrying it across quietly granted something nobody chose.

### Fail-safe sync job
`sync/sync_job.py` (the daily sync): record run → **validate** view schema vs the
registry → **staged load** (COPY into a staging table) → **integrity checks** (row delta
±30%, freshness ≤ 3 days, 7-day revenue penny-match vs BigQuery) → **UPSERT staging into the
live table** by natural key (`date, platform, app_key`) - re-running a date updates in place,
new dates append, aged-out history is retained → refresh `dim_app` → drop staging → bust
`agg:*`. On **any** failure it discards the staged data and leaves the live table untouched
(keeps serving existing data), alerts, and records the reason in `sync_runs`. The
dashboard never shows half-loaded data. The sync also loads the values of any
BigQuery-discovered dynamic columns (see below), so they aren't left NULL.

The **staging table has no primary key**, so a duplicate natural key `(date, platform,
app_key)` in the source view can never crash the load (the historical
`fact_daily_performance_staging_pkey` UniqueViolation). Before merging, staging is
de-duplicated on the natural key - keeping ONE deterministic row per key (highest revenue,
then installs) rather than double-counting - and the number removed is logged **and
alerted**, so a view anomaly is visible and fixable at the source. The **live** table keeps
its primary key, which the UPSERT relies on.

### Sync scheduling, locking & observability

**Schedule.** An in-process scheduler in every backend instance ticks once a minute and
fires the sync when `sync_enabled` is on and the clock reaches `sync_schedule_time`
(HH:MM) interpreted in `sync_timezone` (an IANA zone, e.g. `Asia/Karachi`). Both are
admin-editable under **Admin → Integration**; with no row stored, the registry defaults
apply (`06:00`, `UTC`). "Due" uses `>=`, so a missed tick or a cold start after the
scheduled time still triggers a catch-up run for that day. The daily run is always
`mode=incremental` - it re-pulls the last `sync_window_days` days and **overwrites** that
window; **Full backfill** (`mode=full`) reloads all history and is on-demand only.

**Locking - two locks, distinct jobs.** Both the backend and `sync_job.py` use the Postgres
session advisory key `0x70726F6D`, but for different purposes:

- The **backend** takes it only to serialize the *trigger decision* (skip-check + spawn),
  and **releases it immediately after spawning** the child.
- The **job** takes it itself and holds it for the run, cleanly no-opping if it can't -
  this is what actually prevents two overlapping loads.

> The backend must never hold the lock across the spawn. It used to, handing it to a
> finalizer for the child's lifetime - so the child always lost the lock **to its own
> parent**, logged `another sync holds the advisory lock - skipping this run (no-op)`, and
> exited **0** without writing a `sync_runs` row. Every scheduled run and every "Run daily
> sync" click was a silent do-nothing. See [`CHANGELOG.md`](./CHANGELOG.md), 2026-08-05.

**Exactly-once per day** comes from three things together: the backend lock serializes
triggers, the job's own lock serializes runs, and the scheduler passes `skip_if_ran_after`
- re-checked *under* the lock. That skip is **status-aware**: a `success` ends the day; a
`running` row blocks only while under 2h old (so a stranded row can't wedge the scheduler);
any run under 30 minutes old blocks as backoff, so a **failure retries periodically rather
than burning the whole day**.

**Observability.** The child's stdout/stderr are **streamed into the backend log** prefixed
`[sync]` (the job logs no credentials - only mode, warnings and row counts), and the
scheduler logs **every** tick outcome, not just a successful fire: `not configured` and
`trigger failed` at ERROR, skips at INFO, deduped by reason so a standing condition logs
once instead of every 60 seconds. One command tells you what happened:

```bash
docker compose -f docker-compose.prod.yml logs --since=30m backend \
  | grep -E "scheduler|spawning|\[sync\]|local sync"
```

A healthy backend-triggered run reads: `scheduled sync fired: Sync started.` →
`spawning local sync: mode=…` → `[sync] staging loaded: N rows` → `local sync finished
cleanly`, plus a new `success` row in `sync_runs`.

### Schema reconcile - "Match Database & BigQuery Schema"
When BigQuery's schema changes, admins can bring the Postgres serving layer into line
**without a redeploy** via a button in two places:
- **App Master page** (admin-only) → new BigQuery columns are added to the Postgres copy
  (read-only) and shown immediately.
- **Admin → Integration tab** (metrics fact table) → new BigQuery columns are adopted as
  the `unclassified` metric group and served to **admins only** - never to a non-admin role
  until an owner gives the column a curated metric group in the registry (a deliberate,
  RBAC-reviewed change). This keeps the who-can-see-what guarantee intact.

The reconcile is **additive and non-destructive**: it `ALTER … ADD COLUMN`s new columns
(guarded by a strict identifier pattern + a BigQuery→Postgres type allow-list; unsupported
types like STRUCT/ARRAY are skipped and reported), heals static registry columns missing
from Postgres, and **flags - never drops** - columns that vanish from BigQuery (the column
and its history are kept, marked inactive in `dynamic_columns`). Adopted columns live in the
`dynamic_columns` table; the effective registry refreshes on startup and on the request path
(TTL-guarded) so every worker converges within ~a minute. Both actions are audit-logged,
notify admins, and bust the aggregate cache. Engine: `app/services/schema_reconcile.py`
(+ `fact_schema.py` for the fact-table side).

### Ask-your-data assistant (chatbot)
A natural-language assistant ("what was total revenue last month?", "top 5 apps by ROAS")
that answers **only** from data the asking user is permitted to see. The user picks the model -
**Claude, ChatGPT, Gemini, or Grok** - from whichever providers have an API key configured.
RBAC is not bolted on: every model runs a tool-use loop whose tools execute through the
caller's scoped `QueryBuilder`, so there is **no text-to-SQL and no raw-SQL path**. The same
row-scope + metric-group limits apply identically for every provider, and hold even under
prompt injection (a jailbroken model has no out-of-scope data to reveal). Defense in depth: a
conservative input guardrail refuses obvious jailbreak / "reveal your prompt" / raw-SQL
attempts **before** any model call; the system prompt treats all message + tool content as
untrusted data; and every answer writes a **value-free forensic trace** (metric / dimension /
date window it touched - never the values) to the audit log. Off by default - needs the admin
`chat_enabled` setting **and** ≥1 provider key. Endpoints `POST /chat`, `GET /chat/status`;
engine `services/chat_service.py`, `chat_providers.py`, `chat_guardrails.py`.

### Proactive alerts, daily digest & scheduled reports
- **Anomaly alerts** (revenue drop, spend spike, low ROAS, stale data) evaluated once a day
  after the sync → in-app notifications to admins/execs + email.
- **Daily digest** email (opt-in): revenue, spend, profit, ROAS, top apps.
- **Scheduled report delivery**: email a saved report to yourself daily / weekly / monthly
  (CSV or XLSX). RBAC-safe - it always runs under the **owner's** access and is delivered
  **only** to the owner, so it can never leak data around RBAC.
- All three fire **exactly once cluster-wide** via a DB `job_runs` claim (no duplicate emails
  per instance or per restart). Mail is stdlib SMTP - a graceful no-op when unconfigured.

### Budget pacing & forecasting
- `GET /metrics/pacing` - month-to-date revenue vs the admin target, days elapsed, a linear
  month-end **projection**, attainment %, and on/off-pace - scoped to the caller (the revenue
  target is hidden from roles without revenue permission).
- `GET /metrics/forecast` - daily history plus an OLS linear-trend projection fit on
  **calendar-day offsets** (so gaps in the series don't skew the slope).

### Session security & 2FA
- Self-service **Security page**: whether this sign-in used **2FA** (from the token's
  second-factor claim), recent **device/activity**, and **"sign out of all devices"** -
  which stamps `users.sessions_revoked_at` (tokens issued earlier are rejected **live**) and
  best-effort revokes Firebase refresh tokens.
- **Admins** can force-sign-out any user.
- Optional `require_admin_2fa` setting gates admin actions behind a 2FA sign-in, with a
  **narrow break-glass** (only reading settings + toggling the requirement itself is exempt)
  so an admin can never lock themselves out.

### Observability
Every request gets a **trace id** (`X-Request-ID`, honored from the edge or generated) that
appears on every log line and in the error envelope (so a user can quote it to support);
**structured JSON logs** in production (`LOG_JSON`); optional **Sentry** error reporting
(env-gated, PII off). The frontend has route + global **error boundaries**. Engine
`core/observability.py`.

### App Master editing
The admin App Master page shows every `app_master_v2` column and allows editing exactly six -
`publisher`, `hou`, `pod_owner`, `pod`, `partner_name`, `net_revenue_share` - writing to
BigQuery first, then the Postgres copy, with full change history + undo. The edit drawer uses
**dropdowns** (pick an existing value or type a new one) for the categorical fields, and
**validates** `pod > 0` and `net_revenue_share ∈ [0.0, 1.0]` on both the client and the server.
The page also filters by a **`last_synced_at` date range**, and columns are drag-reorderable
(admin-set global order). The schema-match compares BigQuery names **case-insensitively and
through `bq_name` aliases** (so a column like "Net Revenue Share" with spaces/caps is
recognised as the known `net_revenue_share`, never mis-flagged as missing/unsupported).

### Explore - user-configurable breakdown
An **Explore** page where the user picks the **dimension** (App / Pod / Publisher / Platform /
HOU) and up to 8 **metrics** from dropdowns - every permitted measure, including the full
reported `rpt_*` ladder - rendered as a server-sorted breakdown table under the global filter
bar. Only permitted metrics are offered and the server re-validates every request. The same
`rpt_*` catalog is pickable in the Report Builder.

### Filter bar - searchable dropdowns
The shared `MultiSelect` popover (`components/filters/multi-select.tsx`) shows a **search
box** once a list exceeds 8 options, so picking one of 150+ apps no longer means scrolling.
It applies automatically to **Apps**, **Google package** and **iOS bundle**, while short
lists (Console, HOU, …) stay uncluttered. The search matches the **label or the underlying
value**, so an app is findable by name or by key; already-selected items sort to the top
(ordered from a snapshot taken when the popover opens, so rows don't jump as boxes are
ticked); only the option list scrolls, keeping the search box and Clear pinned. Selection,
the `only` quick-pick, URL sync and the cascading option refresh are unchanged.

**Apps leads the dimension list.** Order, labels and option sources for all ten dimensions
live in one place - `components/filters/dimensions.ts` - and both the inline bar and the
slide-over panel render from it, so the two can't drift apart.

### Filter panel - set everything in one go
`components/filters/filter-panel.tsx` is a **split-screen** panel: the dashboard stays
visible on the left, every filter is on the right. Open it from the **Filters** button in
the bar (it carries the active-filter count).

- The panel edits a **private draft**; **Apply** produces exactly one URL write and one
  refetch. The inline dropdowns commit per click, so setting up a ten-dimension view meant
  ten round trips - this is the difference between "set up my view" and "wait ten times".
- Each dimension is a collapsible section with its own search, a running
  `Showing N of M`, and **Select shown / Deselect shown** - which act on the *filtered*
  list, so "select all" after typing `puzzle` means all puzzle apps, not all 150.
- Date range (the picker below) and Platform sit at the top; **Clear all** resets the draft;
  **Cancel** discards it. Escape closes, and an abandoned edit is never carried forward.
- Apply is disabled until something actually changed, so the panel can't fire a no-op
  refetch.

### Clear filters
A **Clear filters (N)** button appears in the bar only when something is applied, and resets
the date range, Compare, Platform and every dimension to their defaults in one click. The
count comes from `activeFilterCount()` in `lib/filters.ts`, which iterates `LIST_FILTER_KEYS`
rather than a hand-written list - adding a dimension to `Filters` and forgetting to count it
is not possible.

### Date range picker
`components/filters/date-range-picker.tsx` is a Looker-style range picker: preset list down
the left, start/end inputs, a month calendar with the selected range highlighted, prev/next
arrows and a jump-to-month dropdown, a **Compare to previous period** checkbox, and
Cancel/Apply.

**Nothing commits until Apply.** The previous version called `onChange` on every keystroke
and every preset click, so each interaction rewrote the URL and refetched every chart on the
page - that is what made picking a range feel jumpy. The popover now owns a draft and the
page sees a single update. Dates after today are disabled (there is no data ahead of the
sync), and an inverted range blocks Apply with a message rather than silently querying it.

**Named presets are recomputed, never read back from the URL.** A bookmark or saved view
carrying `preset=today&from=2026-08-05` used to render yesterday's numbers under a "Today so
far" label. `parseFilters()` now derives the range from the preset and only trusts stored
dates when `preset=custom` - the label is the intent, the dates are just its cache.

### Responsive layout
- The filter bar keeps **Date · Filters · Platform · Clear · Saved views** at every width;
  the ten inline dropdowns appear from `xl` up and are hidden below it, where the panel is
  the way in. Ten dropdowns wrapped onto a phone is not a filter bar.
- Dropdowns are disabled only until the **first** set of options arrives. Keying that off
  `isFetching` greyed out all ten on every background refresh, mid-click; a refresh now
  shows as a pulse on the Filters button instead.
- The panel is full-width below `sm` and a 26rem drawer above it.
- Wide tables scroll inside their own container (`overflow-x-auto`) rather than pushing the
  page sideways; the ROAS/Ad ROAS/CPI cards stack on narrow screens.

> The desktop sidebar is `hidden md:block`; below `md` navigation comes from the header's
> `MobileNav` drawer. The sidebar itself groups pages under section headings, collapses to
> icon-only from the edge chevron, and keeps its per-user reorder (`nav-order:{user_id}`).
>
> Open: **page grids** are not part of this pass. Where a shared grid is reused inside a
> narrower container, its viewport breakpoints are wrong for that container - see the
> Compare panel-sizing note below for the pattern and the fix.

### Compare - split-screen periods
`/compare` shows two periods side by side under the same dimension filters. Period A is the
global range; Period B is chosen from a **baseline dropdown** - *Previous period*, *Same
period last year* (both follow Period A as it changes) or *Custom range* (pinned until you
change it; switching to Custom seeds from whatever is on screen, so the panel never jumps).
An A-vs-B table shows per-metric change with direction-aware coloring.
`previousWindow()` (`lib/compare.ts`) uses calendar-day arithmetic - raw millisecond math
drifted the window a day across DST changes (covered by `tests/previous-window.test.ts`,
run under three timezones).

If Period B ends up on the *same* range as Period A - which is what picking Period A's own
preset inside Period B's calendar does - every delta is 0.0% and the page looks broken. The
panel now says so explicitly instead of rendering a wall of zeros.

**Top apps by metric** sits below: one line per top-5 app plus a top-10 table, for any of the
14 catalog metrics. Two states are called out rather than drawn as a flat line on the axis -
a metric that is zero for every app (`tech_cost_usd` on most accounts) and a metric with no
day-by-day breakdown, whose period totals are still listed. The *share of top N* column
appears only for additive metrics; summing CPIs, ROAS multiples or percentages has no
meaning, so those metrics get no share column at all.

**Panel sizing.** The KPI and ratio grids pick their column count from *viewport* breakpoints
(`md:`/`xl:`), which is correct on a full-width page but wrong inside a half-width Compare
panel - at `xl` they packed five columns into ~640px and the figures overflowed their cards.
The panels now go side by side only from `2xl`, and the Compare subtree scales the card type
tokens (`--fs-kpi`, `--fs-stat`) down so wide-screen figures fit. The shared components are
untouched, so the Overview renders exactly as before.

### Chart controls - "Adjust chart"
Every chart derives what's adjustable from its own ECharts `option`, and the viewer's
choices are applied as a **pure transform** (`lib/chart-adjust.ts`) - no chart was rewritten,
and everything defaults to off/auto, so an untouched chart renders exactly as its author
designed it. Available from the sliders icon on chart hover:

- **Chart type** - Auto / Line / Bar / Area. **Bar is the house default** - every chart whose
  series are all line/bar renders as a bar chart on first paint (`DEFAULT_CHART_TYPE` in
  `lib/chart-adjust.ts`). *Auto* returns it to the shape its author gave it. Two things are
  deliberately exempt: a chart that **mixes** types on purpose (bars plus a trend or
  break-even line, a scatter with an overlay) keeps its shape - that is exactly the chart
  whose type switcher isn't offered, so nothing becomes unswitchable - and **sparklines**
  under 100px, which host no controls. Pie, heatmap and scatter series are never converted.
- **Y-axis scale** - Auto / Linear / Log.
- **Stacking** - Off / Stacked / **100%**. Offered for Bar and Area only (stacking plain
  lines misleads), greyed out with a hint until one is chosen. 100% normalises each series
  to a share of that index's total - using absolute values, so a negative series such as a
  loss-making Profit still yields sane shares - pins the axis to 0–100% and disables Log,
  since the log of a share is meaningless.
- **Values** - Actual / **Cumulative** / **Avg**. Cumulative is a running total across the
  selected range; Avg is a trailing moving average whose window shortens on short ranges so
  it can't flatten into a line. Mutually exclusive by design.
- **Show data labels** - values printed on points/bars, with overlapping labels hidden
  automatically so a dense daily series stays readable.
- **Series** - show/hide individual series (never the last visible one).

Transforms are applied **before** stacking, so a 100% stacked cumulative chart shows shares
of the running total rather than of the daily values.

### Sync self-healing (promoted dynamic columns)
A BigQuery-discovered dynamic column can later be **promoted** into the curated static
registry (e.g. `apple_account`). Three layers keep that from ever breaking the pipeline:
the sync **skips** any active dynamic column whose name is now static (the registry wins);
`effective_registry()` **dedupes** the same way for serving; and the schema-reconcile
**deactivates** the stale `dynamic_columns` row permanently. (Historically this overlap made
the sync's COPY list carry a column twice - `DuplicateColumn` - and fail daily; the fail-safe
correctly kept serving yesterday's data, and this class of failure is now handled end-to-end.)

---

### Team chat (person-to-person messaging)

`/chat` is Slack-style messaging between platform users - DISTINCT from the AI
ask-your-data assistant (`chat_service.py`), which shares nothing but the word "chat".

- **Model** (`models/messaging.py`): `conversations` (kind direct|group, title,
  `direct_key` = sorted participant-id pair with a UNIQUE index so a DM can never split
  into two threads, denormalised `last_message_at`), `conversation_participants`
  (membership IS the access rule; per-participant `last_read_at` timestamp instead of
  per-message read rows), `messages` (soft-delete via `deleted_at`; sender FK is
  SET NULL so deleting a user never rewrites a conversation).
- **Access rule**: every read/write requires a participant row; non-participants get 404
  (never 403), matching the platform convention. The DM-open race is handled: the unique
  key's IntegrityError loser re-selects and joins the winner's thread.
- **Transport**: polling, not WebSockets (nginx `/api/` passes no Upgrade headers). Open
  thread polls 3s, conversation list 15s, people 30s. Unread counts are ONE grouped query
  per list call, not one COUNT per thread.
- **Delivery ticks**: computed per page from two watermarks (other participants'
  min `last_read_at` and min `last_seen_at`): sent -> delivered (account active since) ->
  read (read marker passed it). Groups only advance when EVERY member has.
- **Groups + invites**: named groups with chosen members; single-use invite codes
  (CSPRNG `secrets.token_hex(4)`, 15-min Redis TTL, atomic GETDEL redemption so a raced
  code admits exactly one person; direct threads REFUSE codes).
- **@mentions**: client sends `mentions: [user_id]`; server drops any id that is not a
  participant of that thread. Rendered highlighted client-side.
- **Admin oversight** (owner decision): admins get a read-only "All chats" tab - list
  every conversation, read any thread, soft-delete any message, hard-delete a whole
  thread (the storage-reclaiming path). No admin send - oversight is seeing, not
  impersonating. EVERY oversight view/delete is audit-logged, so looking leaves a trail.
- **Notifications**: sidebar unread badge, "(N)" tab-title prefix, and a browser
  Notification popup when a new message arrives in an unfocused tab (permission asked on
  first Chat click, never on load).

### Profiles, presence & people

- `users` gained `first_name/last_name/job_title/phone/timezone/last_login_at/
  last_seen_at`; avatars live in a `user_avatars` table (bytes in Postgres - covered by
  the pre-deploy DB backup, no volume to manage). Upload is bounded-read, and the image
  type comes from the file's magic bytes, never the client header. The avatar route
  honours If-None-Match.
- **Presence**: every authenticated request refreshes a self-expiring Redis key (120s);
  online = key exists, away = seen <15 min, offline otherwise. `last_seen_at` persists at
  most once per 5 min (Redis NX throttle; the slot is freed on a failed write).
  `last_login_at` comes from the token's auth_time and only moves forward.
- `/me/profile` (GET/PUT partial-update semantics via exclude_unset), `/me/people`
  (directory + live status; last-login visible to admins only), header presence menu
  ("N online" with per-person last-seen), `/profile` page with avatar upload and an
  Appearance section (see Effects).

### Announcements (broadcast bar)

Admin-published banner shown across every page: body (<=500 chars), level
(info|success|warning|critical), `audience_roles` (Postgres ARRAY; empty = everyone -
filtering is SERVER-side so a client never receives someone else's banner), optional
expiry. Publish/retire are audit-logged; retire is a flag, not a delete. Rendered via a
portal onto <body> (works on mobile where the sidebar host is display:none); per-user
dismissal in localStorage; admins get a floating megaphone composer.

### App Spotlight & UI effects

- `/spotlight`: Tinder-style depth deck of the top-20 apps by revenue (same RBAC'd
  `/metrics/table` endpoint as Apps Explorer) - swipe/arrows/keyboard, real iOS store
  icons via the icon service (`useAppIcons`), branded initial tile otherwise, rolling
  counters for revenue/installs/UA cost, scramble-in titles, conic star-border on the
  active card only.
- **Effects library** (`components/effects/`): `BackgroundFx` - eleven ambient canvas
  backgrounds (aurora, soft-aurora, line-waves, galaxy, pixel-snow, iridescence,
  liquid-chrome, molten-metal, ferrofluid, dark-veil, letter-glitch) behind ONE rAF loop;
  per-user choice + intensity persisted in localStorage (`bg-effect`/`bg-intensity`),
  default none, alpha-capped, paused when the tab is hidden, static frame under
  prefers-reduced-motion. `ClickSpark` - global pointer-click burst (Web Animations API,
  zero idle cost). `ElasticSlider`, `RollingNumber` (numbers settle, never scramble),
  `TextScramble` (titles only - never data).
- **Sidebar**: grouped sections + per-user drag-reorder (`nav-order:{uid}`), collapsible
  to a bubble menu (circular icon buttons, active filled), chat unread badge. The sidebar
  also hosts the portal cluster: AnnouncementBar, ClickSpark, BackgroundFx.

### Delivery pipeline (how code reaches production)

The assistant's sandbox can reach GitHub but NOT GitLab; the server can reach both.
Flow: verify locally (ruff, mypy, pytest, tsc, lint, vitest, next build) -> push to the
GitHub transport branch -> on the server: `git fetch <github-url> dev` +
`git checkout FETCH_HEAD -- <explicit file paths>` (NEVER whole directories - the sandbox
tree is stale for server-drifted files) -> anchored patch scripts for drifted files
(two-pass: verify every anchor exactly once, else write nothing; idempotent via marker)
-> docker build + import smoke test (`python -c "import app.main"`) in a throwaway
container BEFORE anything restarts -> `alembic upgrade head` -> `up -d --build` ->
commit + push to GitLab (`origin`). Alembic revision ids must be NEW - a reused id
silently no-ops the idempotency check (this bit once: d4e5f6a7b8c9 collided with July's
app-master migration).

## 4. Repository structure

```
backend/                 FastAPI service
  app/
    api/v1/              routes: auth, metrics, apps, meta, views, reports, export, admin,
                         layouts, messaging (chat), profile (people/presence), announcements
    core/               config, database, redis, cache, security, rate_limit, metric_registry, fact_table
    models/             SQLAlchemy ORM (identity incl. avatars/presence, rbac, reports,
                        layouts, settings, targets, dim, operations, messaging, announcements)
    schemas/            Pydantic request/response models
    services/           query_builder, auth, admin, reports, metrics, audit, settings, system, cache_warm, schema_reconcile, fact_schema, app_master
  alembic/              migrations (ORM-managed tables; the fact table is sync-owned)
  tests/                pytest suites (RBAC matrix, auth, cache, query builder, financial math, …)
  scripts/              seed_local.py (sample data), create_admin.py (link a Firebase UID → admin)
frontend/                Next.js app
  app/                  App Router pages: overview, revenue, ua, store, apps, data-health, admin, login
  components/           charts, tables, filters, layout, overview/, admin/, ui/ (shadcn),
                        chat/, people/, profile/, spotlight/, compare/, effects/
  lib/                  api client + hooks, filters, formatting, echarts theme, chart-adjust, overview layout
sync/                    daily BigQuery → Postgres job (sync_job.py) + its metric_registry copy
sql/                     bigquery/ (the contract view) + postgres/ (001 init, 002 fact, 003 targets)
docs/                    RUNBOOK-LOCAL, DEPLOY, DESIGN + the audit/review reports
design/                  visual reference (HTML mock, tokens.css, component map)
```

---

## 5. Local setup & run

**Prereqs:** Python 3.12, Node 20, and either Docker Desktop (Postgres + Redis in one
command) or free Neon + Upstash accounts. Full Windows walkthrough:
[`docs/RUNBOOK-LOCAL.md`](./docs/RUNBOOK-LOCAL.md).

Three terminals: **(0)** database + cache, **(1)** backend, **(2)** frontend.

### Required env vars (names only - never commit values)

| Where | Variables |
|---|---|
| `backend/.env` | `ENV`, `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS` |
| backend shell | `GOOGLE_APPLICATION_CREDENTIALS` (path to the Firebase Admin key, **outside** the repo) |
| backend (optional, prod) | `BIGQUERY_PROJECT`, `SYNC_TRIGGER_URL`, `SYNC_TRIGGER_TOKEN` |
| backend (optional - assistant) | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY` (a provider appears in the chat picker only when its key is set), `CHAT_MODEL` |
| backend (optional - email) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` (powers new-app alerts, the digest, and scheduled reports) |
| backend (optional - observability) | `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `LOG_LEVEL`, `LOG_JSON` |
| `frontend/.env.local` | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`, `NEXT_PUBLIC_SHOW_DEMO_WIDGETS` |
| `sync/.env` (real data) | `GCP_PROJECT`, `BQ_VIEW`, `PG_DSN`, `REDIS_URL`, `ALERT_WEBHOOK_URL` |

Each directory ships a `.env.example` (names only) - copy it and fill in your own values.
`NEXT_PUBLIC_*` are exposed to the browser by design (the Firebase web config is public);
**no server secret is ever a `NEXT_PUBLIC_*`**.

### (0) Database + cache

```bash
docker compose up -d        # Postgres on :5432, Redis on :6379
```

### (1) Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv/Scripts/activate
pip install ".[dev]"
cp .env.example .env                                  # set DATABASE_URL / REDIS_URL / CORS_ORIGINS
export GOOGLE_APPLICATION_CREDENTIALS="/path/outside/repo/firebase-admin.json"

alembic upgrade head                                  # create ORM tables + seed roles
PYTHONPATH=. python scripts/seed_local.py             # ~360 rows of sample fact data (no GCP)
PYTHONPATH=. python scripts/create_admin.py --uid <FIREBASE_UID> --email you@example.com

python -m uvicorn app.main:app --port 8000 --reload   # http://localhost:8000/health → {"status":"ok"}
```

### (2) Frontend

```bash
cd frontend
npm install
cp .env.example .env.local                            # set NEXT_PUBLIC_* (API base + Firebase web config)
npm run dev                                            # http://localhost:3000  (development)
# production-style:  npm run build && npm start
```

> **After every `git pull`:** re-run `pip install ".[dev]"` (new runtime deps land in the
> venv only on reinstall) and, in `frontend/`, `npm install`. If the UI behaves oddly or a
> build errors on stale chunks, **`rm -rf frontend/.next`** and rebuild. A **new** backend
> terminal forgets `GOOGLE_APPLICATION_CREDENTIALS` - re-`export` it before `uvicorn` or
> every login 401s.

---

## 6. Adding or changing a metric

Decide which kind first - the two paths touch different layers:

- **Derived / ratio metric** (ROAS, ad_roas, cpi*, *_ecpm, *_ctr, profit_usd,
  organic_install_share, totals like `total_revenue_usd = total_iap_net_usd +
  total_ad_revenue_usd`): compute it **in the BigQuery view**
  (`sql/bigquery/daily_performance_v1.sql`), **not** in Python or TypeScript. If the view
  exposes a new column, register it (next bullet).

- **New raw fact column:**
  1. Add **one `Col(...)` entry** to the registry - in **both**
     `backend/app/core/metric_registry.py` **and** `sync/metric_registry.py` (the parity
     test enforces they match), with its metric group.
  2. Add an **Alembic migration** for the column on the materialized fact table (the sync
     UPSERTs into the live table and no longer rebuilds it, so the column must exist there;
     the sync only creates the table from the registry on a fresh DB where it's absent).
  3. That's it - the registry **generates** the DDL, the per-role Pydantic models, the RBAC
     column filter, and the fact indexes. Don't hand-edit column lists anywhere.

> **Promoting a dynamic column.** If the column already exists in `dynamic_columns` (adopted
> at runtime via schema reconcile), adding it to the static registry makes it appear twice
> unless the stale dynamic row is deactivated. The pipeline handles this itself now - but on
> an older sync image it manifests as `DuplicateColumn: column "x" specified more than once`
> and the sync fails every day. See the troubleshooting table.

Careful-change areas (review before touching): RBAC (scopes, response models,
`permitted_measures`), financial math, the metric registry + drift guard, the sync
pipeline, and auth.

---

## 7. Testing & security posture

**Backend tests** (real Postgres + Redis, fake Firebase verifier):

```bash
cd backend && source .venv/bin/activate
# point TEST_DATABASE_URL / REDIS_TEST_URL at a local Postgres + Redis (CI uses :5432/:6379)
pytest -q
```

Coverage includes the **RBAC matrix** (every role × representative endpoints), auth,
cache (incl. cross-role isolation), the query builder (scope-first, narrow-only,
keyset pagination), financial-ratio math (recomputed from totals, zero-denominator →
null), registry parity, layouts, the admin System tab, the **RBAC-safe chatbot** (both
provider loops, guardrails, forensic trace), **scheduled report delivery**, **pacing /
forecast**, and **session security / 2FA**. CI also runs `ruff`, `ruff format --check`, and
`mypy --strict`.

**Frontend tests** - Vitest + React Testing Library:

```bash
cd frontend && npm test
```

Cover the pure lib (formatting, filters, nav **RBAC gating**, XSS-escape) and feature/
RBAC visibility gating (e.g. the assistant widget only renders when enabled). The frontend
CI also runs `next lint`, `tsc --noEmit`, and `next build`.

`tests/filter-clearing.test.ts` covers the Clear-filters count and the preset recompute -
including a case that walks every `LIST_FILTER_KEYS` entry, so a dimension added to
`Filters` but left out of the constant fails the suite instead of going silently uncounted.
`tests/chart-defaults.test.ts` covers the bar default, the mixed-chart and pie exemptions,
and that `applyAdjustments` never mutates its input.

**Security posture (summary).** Server-side RBAC on every route; row-scope injected into
SQL before data leaves the DB; fully parameterized queries with allow-listed
`group_by`/`sort`/`bucket`; permission-aware aggregate cache; least-privilege DB roles
(`api_service` has INSERT+SELECT only on the append-only `audit_log`; `sync_service` can't
touch RBAC tables); Bearer-token auth (no cookies ⇒ no CSRF); CORS locked to exact origins
(fails closed in prod); per-user rate limiting (the public access-request path is still keyed
to a verified Firebase identity, so there is no anonymous flood route); input caps on date
range and filter lists; all sensitive actions audited.

**Response headers.** `frame-ancestors`/`X-Frame-Options`, `nosniff`, `Referrer-Policy`,
`Permissions-Policy`, HSTS and `X-DNS-Prefetch-Control` are set in
`frontend/next.config.mjs` so they travel with the app, and again in
`docs/nginx-prometheus.conf` with `always` so `/api/` JSON and error responses are covered
too. `X-Powered-By` and `server_tokens` are off. There is deliberately **no `script-src`
CSP**: Next.js emits inline bootstrap scripts, so a real policy needs per-request nonces and
middleware, and a half-written one would either break the app or read as protection that
isn't there.

> This paragraph previously claimed CSP/HSTS/`X-Frame-Options` were in place. They were not,
> anywhere, until 2026-08-07 - a documented control that didn't exist. See CHANGELOG.

**Audit-log integrity.** `client_ip()` prefers `X-Real-IP` (nginx overwrites it from
`$remote_addr`) and falls back to the **last** `X-Forwarded-For` hop. It used to read the
**first** hop, which `proxy_add_x_forwarded_for` leaves attacker-controlled - so any caller
could stamp an arbitrary address on every audit row. Covered by
`backend/tests/test_client_ip.py`.

**Session hand-off.** `SessionCacheGuard` clears the TanStack cache on any Firebase UID
change, so on a shared machine the next person to sign in cannot see the previous user's
figures rendered from cache before their own request returns.

Standing security/quality reviews (audit, red-team, cleanup, enterprise) are maintained for
the project. Known open items: upgrading the Next.js dependency to a patched release;
`verify_id_token()` runs without `check_revoked=True`, so a Firebase-side disable takes up
to an hour to bite (deactivating in the admin panel is immediate, since provisioning is
re-checked from the DB every request); and FastAPI's `docs_url` is not disabled - nginx
routes `/docs` to Next.js so it isn't reachable today, but that is routing luck, not
design.

---

## 8. Deployment

### Branch model - `dev` → `production`

Two long-lived branches, no feature branches:

| Branch | Purpose |
| --- | --- |
| `production` | What the owner makes live. Receives only finished, tested work. |
| `dev` | The working branch. Every change is made and pushed here first. |

The flow: changes land on `dev` → the owner tests them → once finalised, `dev` is merged
into `production`, and `production` is what goes live. Promotion is the owner's call; nothing
is merged to `production` automatically. After a promotion, bring `dev` back in line with
`production` so the next change starts from what is live.

**GitLab is the source of truth.** `production` and `dev` live there, on the deployment
remote. The server is updated by an explicit fetch + `docker compose up -d --build`, so
merging into `production` stages a release; it does not by itself change what is running.

Every change is verified locally before it is delivered (`ruff`, `mypy --strict`, `pytest`,
`tsc --noEmit`, `next lint`, `vitest`, `next build`) and again by the server's docker build,
which type-checks and builds the frontend from scratch.

Backend → **Cloud Run**, frontend → **Vercel**, data → **Neon** + **Upstash**, auth →
**Firebase**. All secrets live in **GCP Secret Manager** (backend) or **Vercel env vars**
(frontend) - **never in the repo**. The daily sync runs as a **Cloud Run Job** on **Cloud
Scheduler**; an optional **Cloud Armor** WAF can front Cloud Run. Step-by-step (including
the env-var reference and a budget alert): [`docs/DEPLOY.md`](./docs/DEPLOY.md).

### Single-VM deployment (docker-compose)

The instance currently in production runs on one Ubuntu host via `docker-compose.prod.yml`
behind nginx, deployed by the GitLab pipeline (`pg_dump` backup → `alembic upgrade head` →
recreate containers → health check). See [`docs/DEPLOY-UBUNTU.md`](./docs/DEPLOY-UBUNTU.md).
In that mode the backend runs the sync **itself** as a subprocess (see §3) rather than
delegating to a Cloud Run Job.

**Container logs must be capped.** Docker's default `json-file` driver keeps logs forever,
and the sync now streams its full output there. Set it globally on the host:

```bash
echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' \
  | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
docker compose -f docker-compose.prod.yml up -d --force-recreate   # containers pick it up
```

Verify with `docker inspect --format '{{.Name}} {{.HostConfig.LogConfig.Config}}' $(docker ps -q)`
- each should report `map[max-file:3 max-size:10m]`.

> `docker-compose.prod.yml` has no per-service `logging:` block, so this daemon-level
> setting is host-local: a rebuilt or migrated host will **not** inherit it. Adding the
> block to the compose file is an open item.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Login worked, now **401 after restarting the backend** | A fresh terminal lost `GOOGLE_APPLICATION_CREDENTIALS`; re-`export` it before `uvicorn`. |
| Everything shows "-" / empty after a DB wipe | Re-seed (`scripts/seed_local.py`) and **re-crown your admin** (`scripts/create_admin.py --uid … --email …`) so your Firebase UID maps to an `admin` with `all` scope. The local seeder preserves existing admins, but a fresh DB needs this. |
| Stale data after a sync / want a clean cache | Clear the aggregate cache: `redis-cli FLUSHDB` (or delete `agg:*`). It also self-busts on each successful sync and expires at the daily boundary. |
| UI build errors / stale chunks after a pull | `rm -rf frontend/.next` then `npm install && npm run build`. |
| `ENOSPC` / out of disk during build | Free space: remove `frontend/.next` and `node_modules` (reinstall), prune Docker (`docker system prune`), clear caches. |
| CORS error in the browser | `CORS_ORIGINS` must be the **exact** frontend origin (e.g. `http://localhost:3000`); restart the backend. |
| Neon connection fails | Use the **pooled** host with the asyncpg driver and TLS: `postgresql+asyncpg://…?ssl=require`. |
| Upstash "Connection closed by server" | The Redis URL must be `rediss://` (TLS), not `redis://`. |
| `npm audit` warnings on install | Expected for dev; **do not** run `npm audit fix --force` (it breaks the build). |
| Sync fails: `UniqueViolation … fact_daily_performance_staging_pkey … (date, platform, app_key) already exists` | The BigQuery view emitted a **duplicate natural key**. Handled automatically now - staging has no PK and is de-duplicated before merge (kept-one is logged + alerted). If you see the old crash, the running sync image predates this fix; redeploy the latest `sync/`. Then investigate the view for the duplicated app/day. |
| Sync fails: `DuplicateColumn: column "x" specified more than once` | A column exists in **both** `dynamic_columns` and the static registry (a promoted dynamic column). Handled end-to-end now; on an older image, deactivate the stale rows: `UPDATE dynamic_columns SET active=false WHERE table_kind='fact' AND name IN (…)`, then redeploy the latest `sync/`. Check with `SELECT name, active FROM dynamic_columns WHERE table_kind='fact';` |
| "Run daily sync" says **"Sync started."** but no new `sync_runs` row appears | The advisory-lock no-op - the backend held the lock across the spawn, so the job backed off and exited 0. Confirm in the logs: `[sync] … another sync holds the advisory lock - skipping this run (no-op)`. Fixed (see §3); if you see it, the running backend image predates the fix. |
| **Scheduled sync never fires** (no `sync_runs` row after the scheduled time) | Check the logs first - the scheduler now reports every outcome. Total silence means `sync_enabled` is off (the only unlogged path). Otherwise verify `sync_schedule_time` / `sync_timezone`: `SELECT key, value FROM app_settings ORDER BY key;` - with no rows, defaults are `06:00` / `UTC`. A bad IANA zone makes `is_due` log an exception and never fire. |
| "Run daily sync" → **Rate limit exceeded** | The heavy sync trigger is capped at 6/min (its own bucket). Read-only Test Connection / Check schema use a separate 20/min bucket, so they no longer starve it. Wait ~60s and click **once** - one run is all that's needed (the job's advisory lock prevents double-runs). |
| Host disk filling up | Check `/var/log` and Docker logs first: `sudo du -xh --max-depth=1 /var/log \| sort -rh \| head`. Cap container logs (§8). Truncate live logs with `truncate -s 0`, never `rm` - a deleted file held open by a running process frees nothing. |

---

*Secrets never belong in this repo. Use `.env*` files locally (gitignored) and Secret
Manager / Vercel env vars in production.*

## Recent additions (2026-08-13)

### Chat contact requests
A new direct thread starts as a **request**, not an open channel. `conversations.status`
(`pending` | `accepted`, default `accepted` so pre-existing threads are grandfathered) plus
`conversations.requested_by` record it. `send_message` refuses a pending thread with 403
(the caller IS a participant, so 404 would be wrong). Only the recipient can accept
(`POST /chat/conversations/{id}/accept`); the requester gets 403 if they try. Removal
(`DELETE /chat/conversations/{id}`) works from either side and covers decline, cancel and
disconnect. Removal hard-deletes ONLY a thread with no messages (freeing the unique
`direct_key` so the pair can start over); a thread with history instead detaches the caller
and is deleted only when nobody remains - one participant must never be able to erase the
other's messages or the oversight record. `POST /chat/conversations/{id}/leave` exits a
group. Pending requests you received count toward the sidebar unread badge.

### Announcements
`announcements.cta_label` / `cta_url` add an optional pill button. The URL is allow-listed
server-side to an in-app path (`/…`, not `//…`) or `https://` - a stored `javascript:` URL
would be persistent XSS in a banner every user sees; the client re-checks before building
an href. The bar renders every active announcement on one continuous plain-text ticker,
pausing on hover. Audience filtering happens in SQL BEFORE the `LIMIT`, so role-targeted
banners cannot push an everyone-banner off the page.

### App Spotlight (incomplete records worklist)
Reads the BigQuery `app_master_v2` table through the existing admin App Master API. An app
appears only when `publisher`, `hou`, `pod`, `pod_owner`, `partner_name` or
`net_revenue_share` is blank; missing fields are flagged and editable in place, with a
dropdown of values already present in the table plus free text for new ones. Saving PATCHes
only the filled fields, so it can never blank a neighbouring column. A numeric `0` counts as
a real value, not a blank.

### Presence, privacy and appearance
Header presence menu (who is online now, plus last-seen). A privacy shield toggle blurs the
whole screen and reveals only a circle following the pointer - shoulder-surfing protection,
not access control (RBAC remains the real boundary). Cursor styles and ambient backgrounds
are per-user preferences on the Profile page.

### Security hardening
Findings from three audits (API, frontend, infrastructure):

- Firebase token verification runs in a worker thread (`anyio.to_thread`); inline it blocked
  the event loop, so junk bearer tokens - each costing a full RSA verification before
  rejection - stalled every other request.
- `pre_auth_rate_limit_middleware` caps requests per source address BEFORE authentication
  (every other limiter keys on an identity, so unauthenticated traffic was unbounded). Fails
  open on Redis errors.
- `client_ip()` believes `X-Real-IP` / `X-Forwarded-For` only when `TRUSTED_PROXY=true`.
  Reached directly, any caller could otherwise forge the IP written into the append-only
  `audit_log` - the field that says who did something.
- `/docs`, `/redoc` and `/openapi.json` are disabled when `ENV=production`.
- `is_active` is re-checked on the cached-context path, so deactivation bites immediately
  rather than up to five minutes later.
- `metrics` query params are bounded (max 25) and reject duplicates, which inflated both
  query cost and the number of distinct aggregate-cache keys.
- Invite codes are refused for direct threads at MINT time; previously `/join` consumed the
  one-shot code before rejecting it.
- Own-message deletion is audit-logged (sends deliberately are not - the messages table is
  that record - but destructive actions are a different class).
- Frontend: notification links must be in-app paths (`router.push` hands a foreign origin to
  `location.assign`, and a `javascript:` URL has an opaque origin); the CPI scatter tooltip
  uses `renderMode: "richText"` so an upstream app name cannot reach `innerHTML`;
  announcement dismissals are scoped per user and shape-checked.
- Dev compose binds Postgres/Redis to loopback; `.gitignore` and the secret-scan denylist
  cover `*.rdb`, `backups/` and Firebase `*adminsdk*.json` key filenames; CI `GITHUB_TOKEN`
  is reduced to `contents: read`.

### Operational note
The deployed tree and the working mirror drift. Before any backend deploy, diff the target
files against the branch being deployed and use anchored patch scripts (verify every anchor
exactly once or abort) for anything that differs - never a directory-wide checkout, and never
overwrite a file the server has evolved.

## Executive Overview widgets (2026-08-17)

### App performance tape
`components/overview/app-tape.tsx` — a trading-desk ribbon across the top of Overview: one
item per app with its name, revenue for the window, absolute change against the **previous
window of equal length** (the same rule the backend uses for period comparison), percent
change, and an UP/DOWN/NEW chip. An app with no prior-period row reads `NEW` rather than a
fabricated 0%. Items link to `/apps/{canonical_key}`.

Two details that were bugs first: the scroll is a CSS animation on a duplicated track, and
`animationPlayState` is set inline **only when paused** — an inline `running` outranks the
`:hover` rule, which is why hover-to-pause silently did nothing. Symbols show the app's own
name; stock-style initials were unreadable for real app names.

Access is inherited, not reimplemented: both reads go through `/metrics/table`, so the
server injects the caller's row scopes. An admin's tape carries every app, a pod owner's
only their pod's.

### HOU Performance replaces Publisher Performance
`hou-table.tsx` already existed, fully written, but was never added to the widget registry
or the default layout — so it never rendered. `scripts/register-hou-widget.py` wires it in;
`scripts/remove-publisher-widget.py` unregisters the publisher-led duplicate. The publisher
component stays on disk unrendered rather than deleted, so re-enabling it is one line.

**Check whether a component already exists before writing one.** The HOU table was built and
forgotten; it cost a wasted build and a broken one to discover that.

### Security page is administrator-only
`scripts/restrict-security-page.py` adds `requiresAdmin` to the nav entry;
`scripts/guard-security-page.py` adds the guard to `security-client.tsx` itself. Both are
needed — hiding a nav link restricts nothing, because a typed `/security` URL still renders
the page. The command palette already filters by role, so the missing `requiresAdmin` flag
was also why the page appeared in search for non-admins.

Note the trade-off: users can no longer see their own active sessions or use "sign out
everywhere". The backend endpoints still answer any authenticated caller with **their own**
session data only — no cross-user leak — so gate them server-side too if the API surface
itself must be admin-only.

## Deployment discipline (learned the hard way)

The deployed tree and any working mirror **diverge**. Three broken builds in one session all
had the same cause: overwriting a whole file the server had evolved past.

- Before touching a shared file, **list the directory and read the file**. `hou-table.tsx`
  imports `ColumnDef`, `METRIC_COLUMNS`, `MetricTable` and `permittedMeasures` from
  `revenue-table.tsx`; a copy lacking those exports breaks the build immediately.
- Use **anchored patch scripts** (`scripts/*.py`) for anything the server owns: each anchor
  must match exactly once or the script aborts having written nothing, and re-running is a
  no-op. Every change that went in cleanly used this; every failure was a file overwrite.
- **Never check out a directory** — explicit file paths only.
- Run the **import smoke test** before restarting anything:
  `docker compose -f docker-compose.prod.yml run --rm backend python -c 'import app.main'`.
- Alembic ids must be **globally new**; a reused id silently no-ops the idempotency check and
  the migration never runs. Two divergent heads are joined with a merge revision whose
  `down_revision` is a tuple of both.
- Recovering a clobbered file: search history for the last good version, e.g.
  `for c in $(git rev-list HEAD -- $F); do git show $c:$F | grep -q "export const X" && echo $c && break; done`.

## Security posture

Verified clean (three parallel audits — API, frontend, infrastructure):
no secrets in the repository or its git history; no SQL injection (every query is
SQLAlchemy Core/ORM with bound parameters); RBAC fails closed on empty scopes; the
404-not-403 convention holds throughout; exports and admin actions are capability-gated and
audit-logged; invite codes resist replay and brute force; the command palette filters by
role and route-owning admin pages carry their own guards.

The Firebase web config in the browser bundle is **public by design** — an identifier, not a
credential. Protection comes from server-side JWT verification plus RBAC on every route, not
from concealing it. The Admin SDK service-account key is the real secret; it is a mounted
file and has never been in git.

Open hardening items, highest impact first:

1. Firebase token verification runs on the event loop, and every rate limiter engages only
   after authentication — junk bearer tokens each cost a full RSA verification and can stall
   the process. Move verification to a worker thread and add an IP-keyed pre-auth ceiling.
2. `client_ip()` trusts `X-Real-IP`/`X-Forwarded-For` unconditionally; reached without the
   nginx in front, the audit log's actor IP is forgeable. Gate on an explicit
   `TRUSTED_PROXY` setting.
3. `/docs`, `/redoc` and `/openapi.json` are enabled in production.
4. Group creation bypasses the chat contact-request consent gate — anyone can add a user to
   a group and message them immediately.
5. No block list: a declined contact request can be re-sent indefinitely.
6. The aggregate cache accepts unbounded distinct parameter combinations with ~24h TTLs.
7. Two database dumps remain in git history (untracked now; purging needs a history rewrite).
8. Dockerfiles use floating base-image tags, so a registry outage blocks every deploy.

## Planned: super-administrator role

A `super_admin` capability above `admin`, able to create, demote and remove administrators.
Design decisions taken before implementation:

- **Second factor**: TOTP is the correct reading of "a key regenerated every login" — a code
  that rotates every 30 seconds, with nothing to intercept and no delivery channel to
  compromise. An emailed one-time code is only as strong as the mailbox; a passkey is
  stronger still. Recovery codes stored hashed and single-use.
- **Step-up re-auth**: the factor is demanded again for destructive actions, not only at
  login, so a stolen session grants nothing.
- **Self-lockout guard**: the last remaining super administrator cannot be removed or
  demoted by anyone, including themselves.
- **Bootstrap by migration**, never through the UI — there must be no self-promotion path.
- Every action audit-logged with actor, target, IP and user agent, into the append-only log
  the `api_service` role cannot UPDATE or DELETE.
- Enforcement server-side only; UI hiding stays cosmetic, as everywhere else.

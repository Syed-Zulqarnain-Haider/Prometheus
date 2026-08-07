# Changelog

Notable changes, newest first. Each entry says **what** changed, **why**, and — where it
matters — **how to tell it's working**, so an incident can be traced back later.

---

## 2026-08-06 (later)

### Security — audit-log IP spoofing, and baseline response headers

**Audit-log IPs were forgeable by the caller.** `client_ip()` read
`X-Forwarded-For.split(",")[0]`. nginx builds that header with
`proxy_add_x_forwarded_for`, which **appends** the real address to whatever the client
sent — so the first entry is attacker-controlled and the last is the one our proxy added.
Any caller sending `X-Forwarded-For: 1.2.3.4` had that address written into the
append-only `audit_log` for every action: login, export, share, admin change. The one
field that records *where* something came from could be set by whoever did it.

It now prefers `X-Real-IP` (nginx sets it from `$remote_addr` with `proxy_set_header`,
which **overwrites** any client value) and falls back to the **last** forwarded hop.
Covered by `backend/tests/test_client_ip.py` — 7 cases including the spoofing one.

> "Last hop" is correct for exactly one reverse proxy, which is what
> `docs/nginx-prometheus.conf` deploys. Adding a CDN in front would make the last hop the
> CDN's address; that needs an explicit trusted-proxy count instead.

**No security response headers anywhere.** No frame protection, so an authenticated admin
could be framed and clickjacked into an action they couldn't see; no `nosniff`; no
referrer policy, so full URLs — which carry filter state: app names, pods, publishers —
leaked to any third party in `Referer`.

Added in two places on purpose: `frontend/next.config.mjs` so they travel with the app and
survive a rebuilt host or a misapplied nginx snippet, and `docs/nginx-prometheus.conf`
(with `always`, so they persist on 4xx/5xx) so `/api/` JSON responses are covered too.
`X-Powered-By` and `server_tokens` are off. Verified against a live `next start`: all seven
headers present, framework header gone.

No `script-src` CSP. Next.js emits inline bootstrap scripts, so a real script policy needs
per-request nonces and middleware; a half-written one would either break the app or read as
protection that isn't there. `frame-ancestors` is safe standalone and is the part that
actually stops clickjacking.

Files: `backend/app/core/http.py`, `backend/tests/test_client_ip.py`,
`frontend/next.config.mjs`, `docs/nginx-prometheus.conf`.

### Admin — row scopes are picked, not typed

`components/admin/scope-editor.tsx`. The scope **type** was already a dropdown; the **value**
was a free-text box, so granting access to an app meant knowing its canonical key by heart
and a typo produced a grant that silently matched nothing.

- The value is now a searchable picker fed from `/apps` — the **dimension** table, so a pod
  or publisher with no rows in the current date window still appears. A scope grant is about
  the org chart, not about who happened to have revenue last month.
- Apps list by **name**, with the canonical key on hover; hou / pod / publisher list their
  distinct values, sorted.
- It stays typeable on purpose. A grant may legitimately name a pod or publisher that has no
  apps mapped to it yet — something the old free-text field could express. Typing a value the
  list doesn't contain offers **Use "…" anyway** rather than silently dropping it.
- Changing the scope type now clears the value. It used to carry across, and a pod name is
  not a publisher name — that quietly granted something nobody chose.
- `all` shows "— whole org" instead of a disabled empty box.
- A stored value the list doesn't recognise is still displayed, never blanked.

Used by both the users panel and the access-requests panel, so both get it.

### Fixed — two of the four frontend bugs from the review

**The UA "CPI vs Install Volume" chart was blank, and the break-even ROAS line never drew.**
Both for the same reason: `lib/echarts.ts` tree-shakes ECharts down to what we register, and
`ScatterChart` and `MarkLineComponent` were never in the list. ECharts renders an empty
canvas for an unregistered series type rather than throwing, so neither failed loudly. Both
registered; the scatter chart draws and the break-even line on Spend vs Revenue appears.

**The TanStack Query cache survived sign-out.** On a shared machine the next person to sign
in saw the previous user's revenue, spend and app list rendered from cache before their own
request returned — figures their RBAC scopes may not entitle them to. The server was never
wrong; the browser was showing someone else's answer. New `SessionCacheGuard`
(`components/layout/session-cache-guard.tsx`, mounted in `app/providers.tsx`) clears the
cache on any UID change, so a direct A→B account switch is covered as well as sign-out.

Files: `frontend/lib/echarts.ts`, `frontend/components/layout/session-cache-guard.tsx`,
`frontend/app/providers.tsx`.

### Charts — bars are the default

Owner decision: the dashboard reads as bars, not lines. `DEFAULT_CHART_TYPE` in
`lib/chart-adjust.ts` is now `"bar"`, so every chart whose series are all line/bar renders as
a bar chart on first paint. **Auto** — the shape the chart's author gave it — is still one
click away in the Adjust chart panel, and `isAdjusted()` compares against the defaults so the
house default doesn't mark every chart as "modified".

Converted: Revenue vs Spend, Revenue composition, Ad-network trend, Spend by network, App
trend, Installs trend. Already bars: Revenue drill, IAP waterfall, Uninstalls/restores.

Two guards keep it from being destructive:

- Retyping is gated on `canSwitchType`, so a chart that **mixes** types on purpose — Monthly
  trend and Spend vs Revenue, both bars plus a line — keeps its shape. That is exactly the
  chart whose type switcher isn't offered, so nothing becomes unswitchable.
- **Sparklines** (under 100px, e.g. the KPI cards' 32px trend) host no controls and keep the
  author's shape. A 32px bar chart the viewer can't switch back reads worse than a 32px line.

Pie, heatmap and scatter are untouched — `retypeSeries` only ever converts cartesian
line/bar, so Revenue progress, Splits, Install mix, the day-of-week heatmap and the CPI
scatter are unaffected.

Files: `frontend/lib/chart-adjust.ts`, `frontend/components/charts/chart.tsx`.

### Filters — a split-screen panel, a Clear button, and a real date picker

**Split-screen filter panel** (`components/filters/filter-panel.tsx`). The dashboard stays
visible on the left, every filter is on the right, opened from a **Filters** button carrying
the active count. It edits a private draft and **Apply** produces exactly one URL write and
one refetch — the inline dropdowns commit per click, so setting up a ten-dimension view used
to mean ten round trips. Each dimension is a collapsible section with its own search,
`Showing N of M`, and Select/Deselect shown, which act on the *filtered* list. Apply is
disabled until something actually changed, so it can't fire a no-op refetch.

**Clear filters.** `activeFilterCount()` in `lib/filters.ts` iterates `LIST_FILTER_KEYS`
rather than a hand-written list, so a new dimension can't go uncounted. The button appears
only when something is applied — a permanently-visible "Clear" on an unfiltered page reads
as broken.

**Date range picker rebuilt** to the Looker layout: preset list, start/end inputs, month
calendar with range highlighting, prev/next + jump-to-month, an inline Compare checkbox (it
was a separate button in the bar), Cancel/Apply. The old version fired `onChange` on every
keystroke and every preset click, so each interaction rewrote the URL and refetched every
chart on the page — that was the "not smooth" complaint. Future dates are disabled; an
inverted range blocks Apply with a message instead of being queried.

**Named presets are now recomputed, not read back from the URL.** A bookmark or saved view
carrying `preset=today&from=2026-08-05` rendered yesterday's numbers under a "Today so far"
label. `parseFilters()` derives the range from the preset and trusts stored dates only when
`preset=custom`.

**Dimension list centralised** in `components/filters/dimensions.ts` — order, labels and
option sources in one place, rendered by both the bar and the panel so they can't disagree.
Apps now leads the list.

### Responsive

- Filter bar: Date · Filters · Platform · Clear · Saved views at every width; the ten inline
  dropdowns show from `xl` up only.
- Dropdowns disable only until the **first** options arrive. Keying that off `isFetching`
  greyed out all ten on every background refresh, mid-click — most of why the filters felt
  unreliable. A refresh is now a pulse on the Filters button.
- Panel is full-width below `sm`, a 26rem drawer above.
- `paid-organic-table` and `network-efficiency` tables scroll in their own container instead
  of pushing the page sideways; the ROAS/Ad ROAS/CPI cards stack below `sm`.

> **Not done:** the app shell. `sidebar.tsx` is `hidden md:block` with no mobile
> alternative — there is no navigation below `md`. `header.tsx`, `sidebar.tsx` and
> `app/(app)/layout.tsx` have all diverged from the GitHub mirror (the live layout has
> `ChatWidget`, `CommandPalette` and `hideGlobalFilters`, none of which exist in the mirror),
> so they were deliberately left untouched rather than overwritten from a stale copy.

Verified with `tsc --noEmit`, `eslint` and a full `next build` — all clean.

---

## 2026-08-06

### Charts — more control over how data is shown

The "Adjust chart" panel gained four options, on top of the existing chart type, y-axis
scale and series toggles. All of them are off by default, so an untouched chart still
renders exactly as its author designed it.

- **Stacking** — `Off` / `Stacked` / `100%`. Stacked sums the series; 100% shows each as a
  share of the total. Offered only for Bar and Area (stacking plain lines is misleading),
  and greyed out with a hint until the viewer picks one of those.
- **Values** — `Actual` / `Cumulative` / `Avg`. Cumulative plots a running total across the
  selected range; Avg is a trailing moving average (up to 7 points, automatically shortened
  for short ranges so a 7-day average over 4 points doesn't flatten into a line). The two
  are mutually exclusive by design.
- **Show data labels** — prints values on the points/bars. Overlapping labels are hidden
  automatically (`labelLayout.hideOverlap`) so a dense daily series stays readable.
- 100% stacking pins the y-axis to 0–100% and disables **Log**, since the log of a share is
  meaningless.

Files: `frontend/lib/chart-adjust.ts`, `frontend/components/charts/chart-controls.tsx`,
`frontend/components/charts/chart.tsx`.

Transforms are applied *before* stacking, so a 100% stacked cumulative chart shows shares of
the running total rather than of the daily values. Everything remains a pure transform over
the ECharts option — no chart had to be rewritten.

### Filters — searchable dropdowns

Picking one app out of 150+ meant scrolling the whole list. The shared `MultiSelect` popover
now has a search box, which also covers **Google package** and **iOS bundle** since they use
the same component.

- Appears only on lists over 8 options, so Console/HOU and other short lists stay uncluttered.
- Matches the label **or** the underlying value — an app is findable by name or by key.
- Already-selected items sort to the top, ordered from a snapshot taken when the popover
  opens, so rows don't jump under the cursor as boxes are ticked.
- Only the option list scrolls; the search box, label and Clear stay pinned.
- Footer shows `Showing N of M · K selected`, with a distinct "No matches" state.

File: `frontend/components/filters/multi-select.tsx`.

### Infrastructure — log rotation and disk

The server hit 88% disk. Two unbounded log sources, neither related to the app:

- **Docker container logs** had no rotation at all. Set globally in `/etc/docker/daemon.json`
  (`max-size: 10m`, `max-file: 3`), so every container is capped at 30 MB. Applied with a
  daemon restart plus `docker compose up -d --force-recreate`.
- **MicroK8s** was writing `Skipping adding existing rule` in a tight loop — **15 GB of
  `/var/log/syslog` in under a day**, far faster than daily logrotate could keep up with. It
  was running no workloads (`kubectl get pods -A` was empty) and has been stopped and
  disabled. logrotate itself was healthy; it was simply out-written.

Disk went 88% → 37%. Also installed **fail2ban** after finding 46,394 failed SSH logins in
`btmp`.

> Note: `docker-compose.prod.yml` still has no `logging:` block. The daemon-level setting
> covers this host, but a rebuilt or migrated host would not inherit it. Worth adding.

---

## 2026-08-05

### Sync — the daily BigQuery → Postgres sync was silently doing nothing

Two independent bugs, both invisible because the job's output was discarded.

**1. `DuplicateColumn` crash.** `apple_account`, `google_play_account`, `rpt_console` and
four `rpt_*` columns existed in **both** `dynamic_columns` and the static metric registry, so
the sync's COPY column list named each one twice and Postgres rejected it. The fail-safe
worked correctly throughout — the live table was never touched and yesterday's data kept
serving. Resolved by deactivating the seven stale `dynamic_columns` rows; they had been
promoted into the static registry and the dynamic copies were leftovers.

**2. Advisory-lock deadlock — the more serious one.** `sync/sync_job.py` acquires
`SYNC_ADVISORY_LOCK_KEY` (`0x70726F6D`) itself and, by design, cleanly no-ops when it can't
get it. `sync_service.run_sync` held the **same key** across the spawn and handed it to the
finalizer for the child's lifetime — so the child always lost the lock **to its own parent**,
logged `another sync holds the advisory lock — skipping this run (no-op)`, and exited **0**
without writing a `sync_runs` row.

Exit 0 meant no error was logged; no run row meant nothing to see in the UI. Every scheduled
06:00 run and every "Run daily sync" click had been a silent do-nothing. Only invocations
that bypass the backend entirely ever succeeded.

The backend's lock now serializes only the *trigger decision* and is released immediately
after the spawn; the job's own lock provides mutual exclusion for the run. A concurrent
trigger that slips into the gap simply spawns a child that no-ops — the intended behaviour.

### Sync — making failures visible

The above took a day to find because nothing was observable. Fixed:

- **`_spawn_local` no longer discards the child's output.** It pipes it and `_drain_local`
  streams it into the backend log prefixed `[sync]`, logging a non-zero exit at ERROR and
  confirming clean exits. `PYTHONUNBUFFERED=1` so a job that dies early still shows why.
  (The original intent was to keep a DSN out of the logs; the job's output contains no
  credentials, only mode/warnings/row counts.)
- **The scheduler logs every tick outcome**, not just a successful fire. `not configured` and
  `trigger failed` at ERROR, skips at INFO, deduped by reason so a standing condition logs
  once rather than every 60 seconds.
- **The skip check is status-aware.** Previously *any* run row at/after the scheduled instant
  blocked a re-fire, so one crash burned the entire day. Now: `success` ends the day; a
  `running` row blocks only while under 2h old (a stranded row can no longer wedge the
  scheduler); any run under 30 minutes old blocks as backoff, so a failure retries
  periodically rather than never.

Files: `backend/app/services/sync_service.py`, `backend/app/services/sync_scheduler.py`.

**How to tell it's working:**

```bash
docker compose -f docker-compose.prod.yml logs --since=30m backend \
  | grep -E "scheduler|spawning|\[sync\]|local sync"
```

A healthy backend-triggered run shows `spawning local sync: mode=…`, then `[sync]` lines
carrying the job's own log, then `local sync finished cleanly` — and a new `success` row in
`sync_runs`. The line that must **not** appear is
`another sync holds the advisory lock — skipping this run (no-op)`.

---

## Known open items

- **Source view emits duplicates.** 1,522 of 11,076 rows (14%) had a duplicate
  `(date, platform, app_key)`. The sync de-duplicates and alerts, but the underlying data
  quality issue in `unified_daily_performance` is unaddressed.
- **~50 view columns are silently dropped** for want of registry entries (`asa_*`, `tiktok_*`,
  `apero_*`, `dlight_*`, `gp_*`, `apple_*`, `rpt_iap_*`, `mint_pub_*`). Adopting these as
  dynamic columns is what caused the `DuplicateColumn` outage — they should be added to the
  registry deliberately instead.
- **`docker-compose.prod.yml` has no `logging:` block** (see 2026-08-06).
- **Admin "show demo widgets" toggle is a no-op.** It is ANDed with `SHOW_DEMO_WIDGETS`, a
  build-time flag from `NEXT_PUBLIC_SHOW_DEMO_WIDGETS`, which deploy docs set to `false`. So
  the toggle is dead in production. Fixing it is an owner decision, not a code fix: the DB
  setting defaults to **True**, so simply dropping the build-time gate would start showing
  fabricated numbers (LTV, cohort ROAS, payback, retention) on the Executive Overview. Either
  flip the DB default to False and make the admin toggle authoritative, or remove the dead
  control from the admin panel.
  (The other three review bugs — blank scatter chart, missing break-even line, cache not
  cleared on sign-out — are fixed above.)
- **`k3s` is running with only its own default system pods** — no application workloads. Idle
  CPU/RAM on a host whose job is four Docker containers.

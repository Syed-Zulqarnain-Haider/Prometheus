# Changelog

Notable changes, newest first. Each entry says **what** changed, **why**, and - where it
matters - **how to tell it's working**, so an incident can be traced back later.

---

## 2026-08-11 (later)

### Branch model: `dev` → `production` (owner decision)

Two long-lived branches replace the previous main + feature-branch flow. `dev` takes every
change; `production` holds only finished, tested work and is what the owner makes live.
Promotion (`dev` → `production`) is the owner's call, never automatic.

Both were created from the up-to-date working branch, so all three heads are identical -
nothing had to be merged and nothing was lost.

**CI would otherwise have gone silent.** `.github/workflows/ci.yml` triggered on `main`
only, so pushes to `dev` and `production` would have run no checks at all. It now watches
`production`, `dev` and `main` on both push and pull request.

`main` is left untouched for now: it is the repository's default branch and cannot be
deleted until the default is switched to `production` in the GitHub settings. It is 28
commits behind `dev`/`production` and holds nothing that is not already in both.

### Compare - self-comparison warning, baseline dropdown, panel sizing, honest empty charts

Reported from a wide screen: KPI figures clipped inside the Compare panels, Period B showing
the same range as Period A with every delta at 0.0%, and the metric dropdown "not working".
Four distinct problems, all fixed:

**Period B could silently equal Period A.** Picking Period A's own preset inside Period B's
calendar pins a custom range identical to A - the table then reads $0 (0.0%) on every row and
looks broken rather than self-referential. The panel now warns explicitly when the two ranges
match. (The date picker itself was fine: it only commits on Apply, which is why nothing
recomputed.)

**Baseline is now a dropdown** (Previous period / Same period last year / Custom range),
replacing the two buttons - and it doubles as the way *out* of a pinned custom range.
Switching to Custom seeds from the range currently on screen, so the panel never jumps.

**Panel sizing - the actual "not responsive" bug.** `KpiRow`/`RatioCards` choose their column
count from *viewport* breakpoints, which is right on a full-width page and wrong inside a
half-width panel: at `xl` five columns were packed into ~640px and the figures overflowed
their cards. The panels now split only from `2xl`, and the Compare subtree scales
`--fs-kpi`/`--fs-stat` down (rem-based, so the header's font control still applies). The
shared components are not forked - the Overview is untouched.

**Top apps by metric - empty states that explain themselves.** "Top apps by Tech cost" drew a
flat line along the axis over a table of $0 rows, which reads as a broken chart. Now a metric
that is zero for every app says so, and a metric with no day-by-day breakdown says the period
totals below are still valid. The *share of top N* column is also gone for non-additive
metrics - summing CPIs, ROAS multiples or percentages produces a meaningless number.

> Worth an eyeball after deploy: the KPI card labelled "Revenue" and the A-vs-B table row
> "Revenue" (`total_revenue_usd`) appeared to disagree in the screenshot. The figures were
> clipped, so this may be nothing; with the sizing fixed the real values are readable.

### Security headers were missing on the LIVE nginx - patch script added

`docs/nginx-prometheus.conf` has carried the edge security headers since the security
pass, but the running server's config was installed BEFORE that and then rewritten in
place by certbot, so it has none: no X-Frame-Options, no CSP, no nosniff, no
Referrer-Policy, no HSTS, and `server_tokens` still on. Next.js sets its own headers for
frontend routes, so the real exposure is `/api/` - every JSON response, including error
responses, goes out bare.

Copying the doc file over the live one would destroy certbot's TLS block, so
`scripts/patch-nginx-headers.py` patches the live file instead:

- resolves `sites-enabled/prometheus` through its symlink (writing through the link would
  replace it with a regular file);
- no-ops if the headers are already there, so it is safe to re-run;
- requires its anchor exactly once and aborts before writing otherwise;
- backs up, writes, runs `nginx -t`, and **restores the backup if the test fails** - a bad
  config can never end up loaded;
- reloads nginx only after a passing test.

HSTS ships uncommented here (unlike the doc file, which targets a fresh HTTP install):
this patches a server already serving HTTPS with a certbot certificate.

Verified against a fixture copy of the live config: headers inserted once, certbot block
and symlink intact, re-run skips, failed `nginx -t` restores, missing anchor writes
nothing.

### Admin System tab: dead demo-widgets toggle removed

Per the owner's decision, the "show demo widgets" control is gone from Operational
settings (`components/admin/system-panel.tsx`). It is filtered out by key via
`RETIRED_SETTING_KEYS` rather than by deleting the `BoolSetting` renderer - the settings
list is server-driven, so the panel must keep rendering every OTHER boolean setting, and a
key-level filter is the smallest change that removes exactly one control.

The backend still ships `show_demo_widgets` in `settings_registry.py` and
`CLIENT_SETTING_KEYS`; nothing reads it in the UI now, and dropping the key is a separate
backend change (registry + `test_system.py` assertions) whenever the owner wants it.

---

## 2026-08-11

### Notification panel restyled AdMob-style: severity cards, New badges, dismiss, sorting

`components/layout/notification-bell.tsx` rebuilt on top of the deployed bell (same hooks,
same unread-count trigger, same deep-link-on-click):

- **Severity-tinted cards** instead of flat rows: 4px left accent + a pale wash of the
  severity colour while unread (`color-mix`, falls back to the plain card where
  unsupported). Critical = negative token, warning = amber, info = accent.
- **"New" badge** on unread cards, coloured by severity; read cards stay listed, dimmed.
- **Dismiss X** on unread cards - marks the notification read WITHOUT following its link
  (there is no delete endpoint; mark-read is the server's dismiss, and the list keeps its
  audit trail).
- **Sort dropdown** with both requested orders: "Sort by date" (newest first, flat) and
  "Sort by type" (Alerts / Warnings / Updates sections, newest first within each).

The mirror's `lib/api-hooks.ts` gained the notifications section (NotificationItem,
useNotifications, useMark*Read) as MIRROR SCAFFOLDING byte-compatible with the deployed
hooks so this compiles in CI - that file must still never be pulled to the server.

### Sidebar merged with the deployed per-user reorder feature - now safe to pull whole

The deployed `sidebar.tsx` turned out to carry a feature the mirror never had: **per-user
nav reordering** (GripVertical toggle in the header, up/down arrows per item, order saved
to localStorage under `nav-order:{user_id}` so it never leaks across account switches).
The earlier grouped-sidebar rewrite would have deleted it; it was held back until the
deployed file could be read, and is now **merged** instead of replaced:

- The reorder feature is preserved verbatim: same storage key, same `applyOrder` ranking
  (unknown/new items keep their default position), same move-arrow UX, same
  `data-tour="nav"` hook for the product tour.
- Groups + collapse land on top: the saved order is applied **before** grouping, so a
  user's reorder decides the order *within* each section. Reorder mode shows the original
  flat list (moving across a section boundary re-ranks into the destination group), and
  entering it requires the sidebar expanded - the grip is hidden while collapsed.
- Collapse (edge chevron, icon-only links with tooltips, "P" brand) works as shipped
  on 2026-08-06; the preference persists via post-hydration-only localStorage.

The 2026-08-06 "do NOT pull sidebar.tsx blindly" note is now RESOLVED: the deployed copy
has been read in full and everything it carried survives, so `git checkout FETCH_HEAD --
frontend/components/layout/sidebar.tsx` is safe.

Correction for the record: an earlier claim that the deployed tree lacked a mobile nav was
wrong - the deployed `header.tsx` mounts `MobileNav` below `md`. The mirror is what lacks
it; nothing to fix on the server.

---

## 2026-08-06 (later)

### Compare - "Top apps by metric" chart + table; sidebar groups + collapse

**Top apps by metric** on `/compare` (AdMob-style): pick any of the 14 catalog metrics and
get one line per top-5 app over Period A, legend chips with per-app period totals matching
the line colors, and a top-10 table with each app's share. Sourced from the same
server-sorted `/metrics/table` endpoint Apps Explorer uses (RBAC + dimension filters apply),
with one per-app timeseries per line. This chart is deliberately `adjustable={false}` - the
house bar default would render five interleaved daily bar sets, which is unreadable for a
multi-app line comparison. The metric catalog moved to `components/compare/metrics.ts`,
shared by the A-vs-B table and this widget so the two can't drift.

**Sidebar: grouped sections + collapse** (`components/layout/sidebar.tsx`): items now sit
under section headings (Overview / Performance / Apps / Reporting / Administration), and an
edge chevron collapses the sidebar to icon-only with tooltips. Grouping is keyed by href
with a visible "More" fallback, so a page this map doesn't know lands in a group instead of
vanishing - the two trees have different nav lists and that must never hide a page. The
collapsed preference persists via localStorage read **post-hydration only** (effect-guarded;
SSR never touches it - the CLAUDE.md localStorage rule exists to protect SSR, and this
pattern cannot break it; owner can veto persistence).

> Sidebar deployment note: the deployed `sidebar.tsx` has drifted from the mirror, so do
> NOT pull it blindly - send the deployed copy first so nothing it carries is lost.

### Compare - split-screen period comparison, and a real previous-period bug

**New `/compare` page** (sidebar, after Reports). Two periods side by side under the same
dimension filters - the comparison isolates the date range, which is the whole point:

- **Period A** is the global date range; the filter bar and the left picker edit the same
  state.
- **Period B** defaults to the immediately-preceding window and **follows Period A** as it
  changes (or *Last year*), so changing A never silently compares against a stale B. Picking
  a custom range pins it.
- Each side renders the same KPI + ratio cards the Overview uses, and an **A vs B** table
  shows the change per metric with direction-aware coloring (a CPI drop is green, a spend
  drop is green, a revenue drop is red). Percent metrics diff in points, not % of a %.
- RBAC-safe: a metric the viewer cannot see is absent from the payload and its row is
  dropped, never zeroed.

**Bug found while building it: `previousWindow()` drifted a day across DST.** It did
calendar math in raw 86,400,000ms blocks. Measured under `TZ=America/New_York`: the
previous window of Mar 15-21 (7 days) came back as **Mar 7-14 - eight days** - so every
Compare-mode ghost overlay and previous-period number was computed off a wrong, longer
window for viewers in DST timezones whenever the baseline crossed a clock change.
(Pakistan has no DST, so PKT viewers were unaffected - anyone abroad was not.) Rewritten
with date-fns calendar arithmetic; `tests/previous-window.test.ts` covers 8 cases and the
suite passes under New York, Berlin and Karachi timezones.

**Also fixed:** the Revenue-targets panel called `setMonths` from inside the `setManual`
state updater. Updaters must be pure - React StrictMode double-invokes them, which
double-applied the redistribution per keystroke in dev.

**Removed:** the "Target line: set in Admin (Step 7)" caption on the Monthly Revenue Trend.
Step 7 shipped long ago, the promised line was never drawn, and a caption promising a
feature that never appears is noise.

The nav entry, the `previousWindow` rewrite and the caption removal live in drifted files,
so they ship via `scripts/patch-compare-page.py` (anchored, abort-safe, idempotent - same
contract as the App Master patch). The page itself is new files.

### App Master - Pod owner, App name and Partner filters

The App Master filter bar had Pod as a bare number box, no Pod owner at all, and app names
reachable only through the free-text Search. Now:

| Filter | Before | After |
|---|---|---|
| **Pod owner** | absent | dropdown |
| **App name** | free-text search only | searchable dropdown |
| **Partner** | absent | dropdown |
| **Pod** | number input | dropdown |

`pod_owners` and `partner_names` were **already** returned by `/app-master/filter-values`
(they populate the edit drawer) and `pods` was returned and unused - so most of the values
existed and nothing was querying them. What was genuinely missing was the filtering side:
`pod_owner` / `app_name` / `partner_name` params on the list route and matching `IN` clauses
in `_apply_filters`. `app_names` is added to `filter-values`.

Package and App ID stay free-text on purpose: each is a substring match across **two**
columns (`android_package` OR `ios_bundle_id`; `canonical_key` OR `apple_id`). A dropdown
would force one exact value from one column and lose that.

Lists over 12 entries get a search box (`FilterPicker`); shorter ones fall back to the plain
dropdown so Platform and HOU don't gain a search box they don't need.

Backend changes ship as `scripts/patch-app-master-filters.py` rather than as edited files,
because those four files exist only in the deployed tree. Every anchor must match exactly
once or the script aborts having written nothing - it can't half-apply across four files -
and re-running it is a no-op. Verified against fixtures built from the live files, including
the abort path.

Files: `frontend/components/app-master/app-master-client.tsx`,
`scripts/patch-app-master-filters.py`.

### Security - dependency vulnerabilities and the unused image optimizer

`npm audit` reported 5 advisories (4 high, 1 moderate), including two that matter for a
dashboard behind auth:

- **Unauthenticated disclosure of internal Server Function endpoints** (GHSA-955p-x3mx-jcvp)
- **SSRF in rewrites via attacker-controlled destination hostname** (GHSA-p9j2-gv94-2wf4)
- Unbounded Server Action payload on the Edge runtime (GHSA-4c39-4ccg-62r3)
- DoS in the Image Optimization API via SVG (GHSA-q8wf-6r8g-63ch)

`next` 15.5.19 -> **15.5.23** clears all four. `nanoid` and `protobufjs` cleared with a
non-breaking `npm audit fix`. This closes the README's standing "upgrade Next.js to a
patched release" item.

**Remaining: 3 high, and they need a major version.** `postcss` and `sharp` are vendored
inside Next and only move on `next@16`, which is a breaking change and not something to do
inside a security patch. What they actually expose:

- `postcss` - build-time CSS processing. The advisories need attacker-controlled CSS or
  `sourceMappingURL` input to the build. Our CSS is in the repo, so there is no path in.
- `sharp` -> libvips (CVE-2026-33327/33328/35590/35591) - reachable through Next's
  `/_next/image` endpoint, which Next serves whether or not you use it.

The dashboard uses **no `next/image` anywhere**, so `images: { unoptimized: true }` now
turns that endpoint off. That removes the reachable path rather than documenting it: the
CVE stays in the lockfile, but nothing serves it.

Verified after the upgrade: tsc, eslint, 30/30 tests, `next build`, and a live `next start`
still returning all six security headers with no `X-Powered-By`.

### Admin - annual revenue target splits itself across the months

The twelve month fields and the annual field were unrelated inputs, so they could disagree
and nothing said so. (They currently do: the saved 2026 targets are a 12,000,000 annual with
13,000,000 sitting in July alone.)

- Entering an **annual target** splits it across all twelve months.
- Editing **any month** fixes that month and the months you have not touched absorb the
  difference, so the twelve always add up to the annual figure.
- Clearing a month hands it back to the automatic split. Manual months are marked and can be
  released by clicking the `manual` tag.
- A **Distribute evenly** button drops every manual value and re-splits.
- A running total line shows `Months total / Annual` and whether they match, so a mismatch is
  visible rather than silent.

Arithmetic is in **integer cents**, not dollars: splitting 12,000,000 twelve ways in floating
point leaves the months summing to 11,999,999.99, and the entire point of the panel is that
the two agree exactly. The indivisible cents are handed out one at a time from January.

Two deliberate refusals: months are **never shown as negative** when the manual ones overshoot
the annual (they are zeroed and the total line flags the overshoot), and **nothing is
redistributed on page load** - every stored month is treated as manual, so opening the page
cannot silently rewrite targets someone already saved. Redistribution starts on the first edit.

The split logic lives in `frontend/lib/target-split.ts` rather than inside the component, so
it is testable: `tests/target-split.test.ts` covers 11 cases, including that the total lands
exactly on the annual for amounts that do not divide by twelve.

Files: `frontend/lib/target-split.ts`, `frontend/components/admin/targets-panel.tsx`,
`frontend/tests/target-split.test.ts`.

### Security - audit-log IP spoofing, and baseline response headers

**Audit-log IPs were forgeable by the caller.** `client_ip()` read
`X-Forwarded-For.split(",")[0]`. nginx builds that header with
`proxy_add_x_forwarded_for`, which **appends** the real address to whatever the client
sent - so the first entry is attacker-controlled and the last is the one our proxy added.
Any caller sending `X-Forwarded-For: 1.2.3.4` had that address written into the
append-only `audit_log` for every action: login, export, share, admin change. The one
field that records *where* something came from could be set by whoever did it.

It now prefers `X-Real-IP` (nginx sets it from `$remote_addr` with `proxy_set_header`,
which **overwrites** any client value) and falls back to the **last** forwarded hop.
Covered by `backend/tests/test_client_ip.py` - 7 cases including the spoofing one.

> "Last hop" is correct for exactly one reverse proxy, which is what
> `docs/nginx-prometheus.conf` deploys. Adding a CDN in front would make the last hop the
> CDN's address; that needs an explicit trusted-proxy count instead.

**No security response headers anywhere.** No frame protection, so an authenticated admin
could be framed and clickjacked into an action they couldn't see; no `nosniff`; no
referrer policy, so full URLs - which carry filter state: app names, pods, publishers -
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

### Admin - row scopes are picked, not typed

`components/admin/scope-editor.tsx`. The scope **type** was already a dropdown; the **value**
was a free-text box, so granting access to an app meant knowing its canonical key by heart
and a typo produced a grant that silently matched nothing.

- The value is now a searchable picker fed from `/apps` - the **dimension** table, so a pod
  or publisher with no rows in the current date window still appears. A scope grant is about
  the org chart, not about who happened to have revenue last month.
- Apps list by **name**, with the canonical key on hover; hou / pod / publisher list their
  distinct values, sorted.
- It stays typeable on purpose. A grant may legitimately name a pod or publisher that has no
  apps mapped to it yet - something the old free-text field could express. Typing a value the
  list doesn't contain offers **Use "…" anyway** rather than silently dropping it.
- Changing the scope type now clears the value. It used to carry across, and a pod name is
  not a publisher name - that quietly granted something nobody chose.
- `all` shows "- whole org" instead of a disabled empty box.
- A stored value the list doesn't recognise is still displayed, never blanked.

Used by both the users panel and the access-requests panel, so both get it.

### Fixed - two of the four frontend bugs from the review

**The UA "CPI vs Install Volume" chart was blank, and the break-even ROAS line never drew.**
Both for the same reason: `lib/echarts.ts` tree-shakes ECharts down to what we register, and
`ScatterChart` and `MarkLineComponent` were never in the list. ECharts renders an empty
canvas for an unregistered series type rather than throwing, so neither failed loudly. Both
registered; the scatter chart draws and the break-even line on Spend vs Revenue appears.

**The TanStack Query cache survived sign-out.** On a shared machine the next person to sign
in saw the previous user's revenue, spend and app list rendered from cache before their own
request returned - figures their RBAC scopes may not entitle them to. The server was never
wrong; the browser was showing someone else's answer. New `SessionCacheGuard`
(`components/layout/session-cache-guard.tsx`, mounted in `app/providers.tsx`) clears the
cache on any UID change, so a direct A→B account switch is covered as well as sign-out.

Files: `frontend/lib/echarts.ts`, `frontend/components/layout/session-cache-guard.tsx`,
`frontend/app/providers.tsx`.

### Charts - bars are the default

Owner decision: the dashboard reads as bars, not lines. `DEFAULT_CHART_TYPE` in
`lib/chart-adjust.ts` is now `"bar"`, so every chart whose series are all line/bar renders as
a bar chart on first paint. **Auto** - the shape the chart's author gave it - is still one
click away in the Adjust chart panel, and `isAdjusted()` compares against the defaults so the
house default doesn't mark every chart as "modified".

Converted: Revenue vs Spend, Revenue composition, Ad-network trend, Spend by network, App
trend, Installs trend. Already bars: Revenue drill, IAP waterfall, Uninstalls/restores.

Two guards keep it from being destructive:

- Retyping is gated on `canSwitchType`, so a chart that **mixes** types on purpose - Monthly
  trend and Spend vs Revenue, both bars plus a line - keeps its shape. That is exactly the
  chart whose type switcher isn't offered, so nothing becomes unswitchable.
- **Sparklines** (under 100px, e.g. the KPI cards' 32px trend) host no controls and keep the
  author's shape. A 32px bar chart the viewer can't switch back reads worse than a 32px line.

Pie, heatmap and scatter are untouched - `retypeSeries` only ever converts cartesian
line/bar, so Revenue progress, Splits, Install mix, the day-of-week heatmap and the CPI
scatter are unaffected.

Files: `frontend/lib/chart-adjust.ts`, `frontend/components/charts/chart.tsx`.

### Filters - a split-screen panel, a Clear button, and a real date picker

**Split-screen filter panel** (`components/filters/filter-panel.tsx`). The dashboard stays
visible on the left, every filter is on the right, opened from a **Filters** button carrying
the active count. It edits a private draft and **Apply** produces exactly one URL write and
one refetch - the inline dropdowns commit per click, so setting up a ten-dimension view used
to mean ten round trips. Each dimension is a collapsible section with its own search,
`Showing N of M`, and Select/Deselect shown, which act on the *filtered* list. Apply is
disabled until something actually changed, so it can't fire a no-op refetch.

**Clear filters.** `activeFilterCount()` in `lib/filters.ts` iterates `LIST_FILTER_KEYS`
rather than a hand-written list, so a new dimension can't go uncounted. The button appears
only when something is applied - a permanently-visible "Clear" on an unfiltered page reads
as broken.

**Date range picker rebuilt** to the Looker layout: preset list, start/end inputs, month
calendar with range highlighting, prev/next + jump-to-month, an inline Compare checkbox (it
was a separate button in the bar), Cancel/Apply. The old version fired `onChange` on every
keystroke and every preset click, so each interaction rewrote the URL and refetched every
chart on the page - that was the "not smooth" complaint. Future dates are disabled; an
inverted range blocks Apply with a message instead of being queried.

**Named presets are now recomputed, not read back from the URL.** A bookmark or saved view
carrying `preset=today&from=2026-08-05` rendered yesterday's numbers under a "Today so far"
label. `parseFilters()` derives the range from the preset and trusts stored dates only when
`preset=custom`.

**Dimension list centralised** in `components/filters/dimensions.ts` - order, labels and
option sources in one place, rendered by both the bar and the panel so they can't disagree.
Apps now leads the list.

### Responsive

- Filter bar: Date · Filters · Platform · Clear · Saved views at every width; the ten inline
  dropdowns show from `xl` up only.
- Dropdowns disable only until the **first** options arrive. Keying that off `isFetching`
  greyed out all ten on every background refresh, mid-click - most of why the filters felt
  unreliable. A refresh is now a pulse on the Filters button.
- Panel is full-width below `sm`, a 26rem drawer above.
- `paid-organic-table` and `network-efficiency` tables scroll in their own container instead
  of pushing the page sideways; the ROAS/Ad ROAS/CPI cards stack below `sm`.

> **Not done:** the app shell. `sidebar.tsx` is `hidden md:block` with no mobile
> alternative - there is no navigation below `md`. `header.tsx`, `sidebar.tsx` and
> `app/(app)/layout.tsx` have all diverged from the GitHub mirror (the live layout has
> `ChatWidget`, `CommandPalette` and `hideGlobalFilters`, none of which exist in the mirror),
> so they were deliberately left untouched rather than overwritten from a stale copy.

Verified with `tsc --noEmit`, `eslint` and a full `next build` - all clean.

---

## 2026-08-06

### Charts - more control over how data is shown

The "Adjust chart" panel gained four options, on top of the existing chart type, y-axis
scale and series toggles. All of them are off by default, so an untouched chart still
renders exactly as its author designed it.

- **Stacking** - `Off` / `Stacked` / `100%`. Stacked sums the series; 100% shows each as a
  share of the total. Offered only for Bar and Area (stacking plain lines is misleading),
  and greyed out with a hint until the viewer picks one of those.
- **Values** - `Actual` / `Cumulative` / `Avg`. Cumulative plots a running total across the
  selected range; Avg is a trailing moving average (up to 7 points, automatically shortened
  for short ranges so a 7-day average over 4 points doesn't flatten into a line). The two
  are mutually exclusive by design.
- **Show data labels** - prints values on the points/bars. Overlapping labels are hidden
  automatically (`labelLayout.hideOverlap`) so a dense daily series stays readable.
- 100% stacking pins the y-axis to 0–100% and disables **Log**, since the log of a share is
  meaningless.

Files: `frontend/lib/chart-adjust.ts`, `frontend/components/charts/chart-controls.tsx`,
`frontend/components/charts/chart.tsx`.

Transforms are applied *before* stacking, so a 100% stacked cumulative chart shows shares of
the running total rather than of the daily values. Everything remains a pure transform over
the ECharts option - no chart had to be rewritten.

### Filters - searchable dropdowns

Picking one app out of 150+ meant scrolling the whole list. The shared `MultiSelect` popover
now has a search box, which also covers **Google package** and **iOS bundle** since they use
the same component.

- Appears only on lists over 8 options, so Console/HOU and other short lists stay uncluttered.
- Matches the label **or** the underlying value - an app is findable by name or by key.
- Already-selected items sort to the top, ordered from a snapshot taken when the popover
  opens, so rows don't jump under the cursor as boxes are ticked.
- Only the option list scrolls; the search box, label and Clear stay pinned.
- Footer shows `Showing N of M · K selected`, with a distinct "No matches" state.

File: `frontend/components/filters/multi-select.tsx`.

### Infrastructure - log rotation and disk

The server hit 88% disk. Two unbounded log sources, neither related to the app:

- **Docker container logs** had no rotation at all. Set globally in `/etc/docker/daemon.json`
  (`max-size: 10m`, `max-file: 3`), so every container is capped at 30 MB. Applied with a
  daemon restart plus `docker compose up -d --force-recreate`.
- **MicroK8s** was writing `Skipping adding existing rule` in a tight loop - **15 GB of
  `/var/log/syslog` in under a day**, far faster than daily logrotate could keep up with. It
  was running no workloads (`kubectl get pods -A` was empty) and has been stopped and
  disabled. logrotate itself was healthy; it was simply out-written.

Disk went 88% → 37%. Also installed **fail2ban** after finding 46,394 failed SSH logins in
`btmp`.

> Note: `docker-compose.prod.yml` still has no `logging:` block. The daemon-level setting
> covers this host, but a rebuilt or migrated host would not inherit it. Worth adding.

---

## 2026-08-05

### Sync - the daily BigQuery → Postgres sync was silently doing nothing

Two independent bugs, both invisible because the job's output was discarded.

**1. `DuplicateColumn` crash.** `apple_account`, `google_play_account`, `rpt_console` and
four `rpt_*` columns existed in **both** `dynamic_columns` and the static metric registry, so
the sync's COPY column list named each one twice and Postgres rejected it. The fail-safe
worked correctly throughout - the live table was never touched and yesterday's data kept
serving. Resolved by deactivating the seven stale `dynamic_columns` rows; they had been
promoted into the static registry and the dynamic copies were leftovers.

**2. Advisory-lock deadlock - the more serious one.** `sync/sync_job.py` acquires
`SYNC_ADVISORY_LOCK_KEY` (`0x70726F6D`) itself and, by design, cleanly no-ops when it can't
get it. `sync_service.run_sync` held the **same key** across the spawn and handed it to the
finalizer for the child's lifetime - so the child always lost the lock **to its own parent**,
logged `another sync holds the advisory lock - skipping this run (no-op)`, and exited **0**
without writing a `sync_runs` row.

Exit 0 meant no error was logged; no run row meant nothing to see in the UI. Every scheduled
06:00 run and every "Run daily sync" click had been a silent do-nothing. Only invocations
that bypass the backend entirely ever succeeded.

The backend's lock now serializes only the *trigger decision* and is released immediately
after the spawn; the job's own lock provides mutual exclusion for the run. A concurrent
trigger that slips into the gap simply spawns a child that no-ops - the intended behaviour.

### Sync - making failures visible

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
carrying the job's own log, then `local sync finished cleanly` - and a new `success` row in
`sync_runs`. The line that must **not** appear is
`another sync holds the advisory lock - skipping this run (no-op)`.

---

## Known open items

- **Source view emits duplicates.** 1,522 of 11,076 rows (14%) had a duplicate
  `(date, platform, app_key)`. The sync de-duplicates and alerts, but the underlying data
  quality issue in `unified_daily_performance` is unaddressed.
- **~50 view columns are silently dropped** for want of registry entries (`asa_*`, `tiktok_*`,
  `apero_*`, `dlight_*`, `gp_*`, `apple_*`, `rpt_iap_*`, `mint_pub_*`). Adopting these as
  dynamic columns is what caused the `DuplicateColumn` outage - they should be added to the
  registry deliberately instead.
- **`docker-compose.prod.yml` has no `logging:` block** (see 2026-08-06).
- **Admin "show demo widgets" toggle is a no-op.** It is ANDed with `SHOW_DEMO_WIDGETS`, a
  build-time flag from `NEXT_PUBLIC_SHOW_DEMO_WIDGETS`, which deploy docs set to `false`. So
  the toggle is dead in production. Fixing it is an owner decision, not a code fix: the DB
  setting defaults to **True**, so simply dropping the build-time gate would start showing
  fabricated numbers (LTV, cohort ROAS, payback, retention) on the Executive Overview. Either
  flip the DB default to False and make the admin toggle authoritative, or remove the dead
  control from the admin panel.
  (The other three review bugs - blank scatter chart, missing break-even line, cache not
  cleared on sign-out - are fixed above.)
- **`k3s` is running with only its own default system pods** - no application workloads. Idle
  CPU/RAM on a host whose job is four Docker containers.

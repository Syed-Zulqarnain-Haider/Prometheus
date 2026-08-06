# Changelog

Notable changes, newest first. Each entry says **what** changed, **why**, and — where it
matters — **how to tell it's working**, so an incident can be traced back later.

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
- **Frontend bugs found during review, not yet fixed:** the UA "CPI vs Install Volume" chart
  renders blank (`ScatterChart` never registered with ECharts); the break-even ROAS line never
  draws (`MarkLineComponent` never registered); the admin "show demo widgets" toggle is a
  no-op (ANDed with a build-time env var that is `false`); the TanStack Query cache is not
  cleared on sign-out, so on a shared machine the next user briefly sees the previous user's
  cached data.
- **`k3s` is running with only its own default system pods** — no application workloads. Idle
  CPU/RAM on a host whose job is four Docker containers.

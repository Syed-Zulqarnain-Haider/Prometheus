#!/usr/bin/env python3
"""Document the decision-support features in README.md.

Nine features shipped in this batch and none of them existed in the README, which is the
document an engineer reads before touching the code. Everything here describes behaviour
that is already in the repository - no roadmap, no "coming soon".

Also fills in two env vars the table never listed: SMTP_SECRET_KEY (the app's at-rest
encryption key, which now gates the Discord webhook as well as the SMTP password) and
DISCORD_WEBHOOK_URL.

Anchored: every anchor must appear EXACTLY once or NOTHING is written. Idempotent.
Documentation only - nothing to rebuild, nothing to migrate.
"""

from __future__ import annotations

import sys
from pathlib import Path

README = Path("README.md")

PURPOSE_ANCHOR = """- **Purpose:** a single, governed analytics surface for mobile-app performance — the
  "Executive Overview" plus Revenue, UA, Store, Apps Explorer, and App Detail pages.
"""
PURPOSE_NEW = """- **Purpose:** a single, governed analytics surface for mobile-app performance — the
  "Executive Overview" plus Revenue, UA, Store, Apps Explorer, and App Detail pages,
  a phone-first **Today** screen, and a decision-support layer that explains *why* a
  number moved rather than only showing that it did (see §3).
"""

# Extend the existing alerts section rather than adding a competing one.
ALERTS_ANCHOR = """- All three fire **exactly once cluster-wide** via a DB `job_runs` claim (no duplicate emails
  per instance or per restart). Mail is stdlib SMTP — a graceful no-op when unconfigured.
"""
ALERTS_NEW = """- **Watchlist alerts** (opt-in, `watchlist_alerts_enabled`): star an app and the same daily
  pass notifies **you** about unusual movement on it — evaluated through *your* resolved
  context, so a viewer is told about installs, never a revenue figure they cannot see on
  screen.
- **Discord delivery** — the digest and the alerts also post to a Discord channel as
  embeds. The webhook URL is a credential (anyone holding it can post as this app), so it
  is Fernet-encrypted at rest, **never** returned by any endpoint or written to a log,
  and validated against Discord's own hosts before storage — a webhook field that will
  POST anywhere is an SSRF primitive handed to whoever holds the admin panel. Without an
  at-rest key the service **refuses** to store it rather than writing plaintext;
  `DISCORD_WEBHOOK_URL` in the environment still works in that state. Configure at
  **Admin → System → Discord**; engine `services/discord_service.py`.
- All of these fire **exactly once cluster-wide** via a DB `job_runs` claim (no duplicate
  emails per instance or per restart). Mail is stdlib SMTP — a graceful no-op when
  unconfigured, and a Discord outage never costs anyone the email.
"""

PACING_ANCHOR = """- `GET /metrics/forecast` — daily history plus an OLS linear-trend projection fit on
  **calendar-day offsets** (so gaps in the series don't skew the slope).
"""
PACING_NEW = """- `GET /metrics/forecast` — daily history plus an OLS linear-trend projection fit on
  **calendar-day offsets** (so gaps in the series don't skew the slope).
- **Scoped targets & UA budgets** (`scoped_targets`, `GET /scoped-targets/pacing`) — the
  org-wide goal is a number for the board; these are the goals the person who owns a pod
  is actually measured against, plus the budget half of the question, which had no goal at
  all before. A target is *(kind, scope, month, amount)*: a **revenue goal** or a **UA
  budget**, org-wide or for one pod / app / publisher / HOU.
  **Direction is per kind and is data, not a UI convention** — running ahead of a revenue
  target is good, running ahead of a UA budget is overspending, so `higher_is_better`
  ships in the payload and no consumer has to guess. Visibility follows the caller's row
  scopes *and* their metric permissions (a target is a revenue figure). Monthly only, so
  there is never a second answer to "what is the goal". Set at **Admin → Targets &
  budgets**; shown by the *Targets & budgets* Overview widget with a tick where a straight
  line says today should be.
"""

# The new block goes between "Explore" and "Sync self-healing" so the decision-support
# features read together, after the query surfaces they build on.
FEATURES_ANCHOR = "### Sync self-healing (promoted dynamic columns)\n"
FEATURES_ADD = """### "What moved" — contribution analysis with a written summary
The KPI card says revenue is down 34%. The only question anyone asks next is **which
apps**, and answering it used to mean opening Apps Explorer and diffing two periods by
hand. `GET /metrics/contribution` does the diff in **one** query, over the **same**
previous-period window the KPI cards use — so the per-entity deltas reconcile with the
headline instead of drifting from it — and returns current, previous, delta and change
percent per app / pod / publisher / platform / HOU, biggest movers first by **absolute**
delta (so the list keeps the biggest moves in *either* direction).

The Overview panel renders it two ways. A **sentence written from the numbers below it —
no LLM**: a generated summary must never be able to invent a figure that contradicts the
list under it, and a deterministic sentence is also instant, free and testable (the
assistant stays for open-ended questions; this is arithmetic). Then the movers themselves,
declines first, each bar sized against the **biggest mover** rather than against the net
total — when gains and losses roughly cancel, which is exactly the case this panel exists
to explain, shares of a near-zero net are meaningless. Coverage is stated honestly: the
list is a top N, so the panel says how much of the move those N explain.

`change_pct` is **null**, never 0, when the previous window was zero — a percentage off
nothing is a division artefact, not a fact about the business.

### Timeline notes (chart annotations)
Revenue steps down on the 14th and stays down; six weeks later nobody remembers the 14th
is the day UA was paused on the two biggest apps, so the same question gets
re-investigated from scratch. An annotation is one dated sentence pinned to the charts.

Notes carry a scope of the **same shape a user scope has** (`all` / app / pod / publisher /
HOU) and are readable only by callers whose own scopes cover them — "UA paused on Alpha"
would otherwise tell a scoped user that an app called Alpha exists, which is precisely what
row scoping prevents. **Writing goes through the same rule**, because the write side is
where an existence probe slips past the read gate; a scoped user also cannot write
org-wide. Out-of-scope rows return **404, never 403**. Editing and deleting are the
author's or an admin's — shared context must not be quietly rewritable by anyone who can
read it — and every create/update/delete is audit-logged.

Markers are drawn on **daily** charts only (Overview *Revenue vs Spend*, every App Detail
trend). A monthly bucket cannot place "the 14th" anywhere honest, so any date not on the
axis is dropped rather than nudged to a neighbour.

### Per-app anomalies & watchlist
The fleet-wide alerts answer "is the business okay". They structurally cannot answer "is
**my** app okay" — one app can halve while the fleet total moves two percent.
`GET /metrics/anomalies` scores each entity against **its own** recent history and returns
the outliers; starring an app adds it to your watchlist, and the daily pass notifies you
about it.

Why not a percentage change: a day-over-day percentage flags every app with a weekend and
misses the slow app that quietly halves. The baseline is the **median** of the trailing
four weeks with a **median absolute deviation** scale — both robust, so one spike in the
history does not inflate the yardstick and hide the next one, which is exactly what a mean
and a standard deviation do. The score is the standard robust *z*, `0.6745·(x−median)/MAD`.

Three guards keep it from becoming noise people filter to a folder:
- A **flat** series has MAD = 0 and no score exists — reported as `score: null` and decided
  on the relative move, never a fabricated infinity that would sort to the top forever.
- A move must **also** clear a minimum percent of the baseline, or an app earning four
  dollars a day is "anomalous" every time it earns six.
- The day scored is the **latest complete** one (`services/day_completeness.py`). Scoring
  the newest partial day — Apple lags 2–3 days — would report the whole catalogue as
  collapsing every morning.

The baseline window is **fixed**, not the selected date range, so an app is never an
anomaly on one page and fine on another because of a date picker. You can only star an app
you can already see (404, not 403), the list is re-filtered through current scopes on every
read, and it is capped so neither the notification nor the daily pass is unbounded.

### Portfolio benchmarks
Every ratio on the dashboard is an absolute number with no context: 1.4× ROAS, a 22%
margin, a $0.83 CPI — good or bad? `GET /metrics/benchmarks` ranks each app against its
peers on **ROAS, profit margin, CPI and revenue-per-install**, shown as *How this app
ranks* on App Detail and as a best/worst leaderboard on Overview.

- The peer set is everything in the current filter and scope **except** the app narrowing —
  selecting one app would make it its own peer group and every percentile would be 50.
  Every other filter is honoured, so a pod owner filtering to their pod is ranked inside
  their pod.
- A **zero denominator is excluded**, not ranked as zero. An app with no spend has no ROAS,
  and ranking it "worst" would push every real app up a quartile and flatter the portfolio.
- Quartiles are **withheld below four** ranked apps: "top quartile" out of three means "one
  of the three of us".
- **Direction is inverted server-side for cost-like ratios**, so a higher percentile always
  means a better app and no UI has to know which way round CPI runs.
- A benchmark is computed only when **both** component measures are permitted.

### Today — the phone screen
The dashboard is built for a desk; the installed PWA is not. `/today` answers the four
things anyone checks on a phone — what happened, what moved it, is anything wrong, are we
on track — in one column, composed entirely from endpoints that already enforce RBAC.

The day shown is the **latest complete** one, never `MAX(date)`, which is a partial day
while Apple's numbers land. That is also why `GET /meta/freshness` now reports
`latest_complete_date`: the concept existed in three services and nowhere in the API, so
every client that wanted "which day is this data actually about" had to guess, and the
obvious guess is the wrong one. The global filter bar is hidden here on purpose — Today is
a fixed window, and a date picker that silently did nothing would be worse than none.

"""

ENV_ANCHOR = """| backend (optional — observability) | `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `LOG_LEVEL`, `LOG_JSON` |
"""
ENV_NEW = """| backend (optional — observability) | `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `LOG_LEVEL`, `LOG_JSON` |
| backend (optional — secrets at rest) | `SMTP_SECRET_KEY` — a Fernet key. The app's **single** at-rest encryption key (named after the feature that needed it first): without it the admin panel refuses to store the SMTP password or the Discord webhook rather than writing either in plaintext |
| backend (optional — Discord) | `DISCORD_WEBHOOK_URL` — fallback destination for the digest and alerts. An admin-stored (encrypted) webhook takes precedence; this keeps delivery working before anyone opens the page, and while no at-rest key is configured |
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not README.exists():
        die(f"{README} not found - run from the repository root")

    text = README.read_text()
    if '### "What moved" — contribution analysis' in text:
        print(f"{README}: already documented")
        return

    edits = [
        (PURPOSE_ANCHOR, PURPOSE_NEW),
        (ALERTS_ANCHOR, ALERTS_NEW),
        (PACING_ANCHOR, PACING_NEW),
        (FEATURES_ANCHOR, FEATURES_ADD + FEATURES_ANCHOR),
        (ENV_ANCHOR, ENV_NEW),
    ]
    for anchor, _ in edits:
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{README}: expected exactly one {first!r}, found {text.count(anchor)}")

    for anchor, replacement in edits:
        text = text.replace(anchor, replacement, 1)
    README.write_text(text)
    print(f"patched {README}: nine decision-support features + two env vars documented")


if __name__ == "__main__":
    main()

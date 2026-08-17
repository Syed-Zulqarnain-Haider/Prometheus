#!/usr/bin/env python3
"""Stop the digest and anomaly alerts reporting on partially-loaded days.

Both services select the two most recent dates with:

    FROM fact_daily_performance GROUP BY date ORDER BY date DESC LIMIT 2

which takes whatever is newest regardless of whether the sync has finished filling it.
Confirmed on live data (2026-08-17):

    2026-08-16    56 rows    $0.00      <- partial, source lag
    2026-08-15   118 rows    $1,065.97  <- partial
    2026-08-14   235 rows    $5,135.21  <- complete
    2026-08-13   247 rows    $5,860.67  <- complete

So the digest compared two partial days and reported "$0, -100%", and the anomaly
checks would have raised a critical "revenue fell 100%" plus a low-ROAS alert - all
fabricated from data that simply had not landed yet. Apple lags 2-3 days by design
(see CLAUDE.md), so this is the normal state of the newest rows, not an incident.

The fix is a HAVING clause: a day qualifies only if its row count reaches 80% of the
trailing 7-day median. On the numbers above the median is ~240 and the threshold ~192,
so both partial days drop out and the pair becomes 2026-08-14 vs 2026-08-13 - a
truthful -12%. The SELECT lists are untouched, so nothing else about either query
changes.

Why the median rather than a fixed row count: the app catalogue grows, and a hardcoded
threshold silently rots. Why 80%: complete days here vary 235-247 rows, and a genuinely
short-but-complete day (a holiday, an app retired) should still report.

NOTE - this fixes the FIRST half of the problem: neither service will report on a
partial day again. The second half (raising an explicit "sync incomplete" alert rather
than silently skipping) is a change to the alert-emitting logic and is deliberately
NOT bundled here - it needs its own review.

Anchored: the target line must appear EXACTLY once per file or nothing is written.
Idempotent. Restart the backend afterwards; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

DIGEST = Path("backend/app/services/digest_service.py")
ALERTS = Path("backend/app/services/alerts_service.py")

# The identical tail both queries end with.
ANCHOR = '    f"FROM {_FACT} GROUP BY date ORDER BY date DESC LIMIT 2"\n'

# A day counts as complete when it reaches this share of the trailing 7-day median row
# count. One constant, referenced by both queries, so it is tuned in a single place.
CONST_ANCHOR = '_FACT = "fact_daily_performance"\n'
CONST_ADD = '''
# A date is COMPLETE when its row count reaches this share of the trailing 7-day median.
# The newest fact dates are routinely partial (Apple lags 2-3 days), and reporting on them
# produced "$0 / -100%" digests and false revenue-collapse alerts. Median rather than a
# fixed count so the threshold follows the catalogue as it grows.
_COMPLETE_DAY_RATIO = 0.8
_RECENT_DAYS_FOR_MEDIAN = 7
'''

REPLACEMENT = '''    f"FROM {_FACT} GROUP BY date "
    # Only days the sync has actually finished: at least _COMPLETE_DAY_RATIO of the
    # trailing median row count. Without this the two newest (partial) days were
    # compared against each other and reported as a total collapse.
    f"HAVING COUNT(*) >= COALESCE((SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY c) "
    f"FROM (SELECT COUNT(*) AS c FROM {_FACT} GROUP BY date "
    f"ORDER BY date DESC LIMIT {_RECENT_DAYS_FOR_MEDIAN}) recent), 0) * {_COMPLETE_DAY_RATIO} "
    f"ORDER BY date DESC LIMIT 2"
'''


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for path in (DIGEST, ALERTS):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    texts: dict[Path, str] = {}
    for path in (DIGEST, ALERTS):
        text = path.read_text()
        if "_COMPLETE_DAY_RATIO" in text:
            print(f"{path}: already fixed")
            continue
        if text.count(ANCHOR) != 1:
            die(f"{path}: expected exactly one {ANCHOR.strip()!r}, found {text.count(ANCHOR)}")
        if text.count(CONST_ANCHOR) != 1:
            die(f"{path}: expected exactly one {CONST_ANCHOR.strip()!r}")
        texts[path] = text

    if not texts:
        print("already fixed - nothing to do")
        return

    # Validate BOTH files before writing EITHER: one service reporting on complete days
    # while the other still reads partial ones would be worse than neither.
    for path, text in texts.items():
        text = text.replace(CONST_ANCHOR, CONST_ANCHOR + CONST_ADD, 1)
        text = text.replace(ANCHOR, REPLACEMENT, 1)
        path.write_text(text)
        print(f"patched {path}")

    print("\nBoth services now report on the last COMPLETE day.")
    print("On the live data that moves them from 2026-08-16 ($0) to 2026-08-14 ($5,135).")
    print("Restart the backend: docker compose -f docker-compose.prod.yml up -d --build backend")


if __name__ == "__main__":
    main()

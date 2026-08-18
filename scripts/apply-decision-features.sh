#!/usr/bin/env bash
# Apply the decision-support feature batch, in dependency order.
#
# The order is not cosmetic. Each patch anchors on structure the previous one created:
# the Overview widget registry grows one entry at a time, and the four migration-bearing
# patches chain onto each other's revision. Running them out of order aborts safely
# (every script validates all its anchors before writing anything), but it will not get
# you a working tree.
#
# The FIRST entry is the one this batch turned out to be missing on the server: the
# contribution endpoint was committed but never applied, so the UI patch that calls it
# went in against an endpoint that did not exist. It is listed here so the batch is
# self-contained rather than assuming anything about what a previous deploy ran.
#
# Every script is idempotent: a second run reports "nothing to do" and changes nothing,
# including the shared migration head pin. So this is safe to re-run after a partial
# failure - fix the cause and run it again.
#
# Usage, from the repository root:
#   bash scripts/apply-decision-features.sh
#
# Exit code is the first failing script's, so it drops into a deploy chain with &&.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -d backend/app ] || { echo "run from the repository root" >&2; exit 1; }

SCRIPTS=(
  add-contribution-analysis    # 1    /metrics/contribution - the query behind it all
  add-contribution-tests       # 1    and its tests, in the same pass
  add-contribution-ui          # 1+2  "What moved" panel + the written summary
  add-chart-annotations        # 3    timeline notes on the daily charts
  add-watchlist-anomalies      # 4    per-app anomalies + the personal watchlist
  add-portfolio-benchmarks     # 5    rank each app against its peers
  add-scoped-targets-pacing    # 6+7  per-pod/app goals and UA budgets
  add-today-screen             # 8    the phone-first Today screen
  add-discord-delivery         # 9    digest + alerts into Discord
  document-decision-features   #      README
)

# Cosmetic patches, run AFTER the batch and deliberately NON-FATAL. A class-string fix
# that cannot find its anchor is worth reporting, and is never worth holding back a
# working feature deploy that has already applied.
COSMETIC=(
  fix-sidebar-alignment        #      collapsed rail: centre the icons and the logo
)

for name in "${SCRIPTS[@]}"; do
  echo "==> ${name}"
  python3 "scripts/${name}.py"
done

skipped=""
for name in "${COSMETIC[@]}"; do
  echo "==> ${name} (cosmetic)"
  python3 "scripts/${name}.py" || skipped="${skipped}${name} "
done

echo
if [ -n "$skipped" ]; then
  echo "!! Cosmetic patch(es) did NOT apply: ${skipped}"
  echo "   The abort message above names the anchor that missed. Every FEATURE patch"
  echo "   IS applied - carry on with the build, and send that line on so the cosmetic"
  echo "   patch can be re-anchored."
  echo
fi
echo "All feature patches applied. Next:"
echo "  1. rebuild the images"
echo "  2. alembic upgrade head   (4 new tables: chart_annotations, watchlist_items,"
echo "     scoped_targets, discord_config)"
echo "  3. ./scripts/run-backend-tests.sh   - the gate, before anything is restarted"

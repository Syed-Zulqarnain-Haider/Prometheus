#!/usr/bin/env bash
# The whole deploy, in the repository, so the command you paste is one short line and
# nothing can be mangled by a terminal wrapping a ten-line shell continuation.
#
# Order matters and every step gates the next:
#
#   1. preflight  - dry-runs the entire patch chain against a throwaway COPY of this
#                   tree. If any anchor misses, we find out here, with nothing changed.
#   2. apply      - the patches, for real, on this tree.
#   3. build      - the images.
#   4. migrate    - alembic upgrade head, using the NEW image, with db+redis up.
#   5. TEST       - the full backend suite against a throwaway Postgres + Redis. This is
#                   the gate: if it fails, nothing is restarted and nothing is pushed.
#   6. restart    - only now.
#   7. commit+push to the deployment remote.
#
# Nothing before step 6 touches the running containers.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"
MSG="${1:-feat: decision-support batch (contribution, timeline notes, anomalies, benchmarks, targets, today, discord) + sidebar alignment}"

echo "### 1/7 preflight (dry run - nothing in this tree is touched)"
bash scripts/preflight.sh

echo
echo "### 2/7 applying the patches"
bash scripts/apply-decision-features.sh

echo
echo "### 3/7 building images"
$COMPOSE build

echo
echo "### 4/7 migrating (db + redis up first, migration runs on the NEW image)"
$COMPOSE up -d db redis
$COMPOSE run --rm backend alembic upgrade head

echo
echo "### 5/7 backend test suite - THE GATE"
./scripts/run-backend-tests.sh

echo
echo "### 6/7 restarting"
$COMPOSE up -d
sleep 45
$COMPOSE ps

echo
echo "### 7/7 committing and pushing"
git add -A
git commit -m "$MSG" || echo "nothing to commit"
git push origin dev

echo
echo "DONE. New tables: chart_annotations, watchlist_items, scoped_targets, discord_config."
echo "Still needs you: SMTP_SECRET_KEY (for the Discord webhook), real values in"
echo "Admin > Targets & budgets, and 'Watchlist anomaly alerts' in Admin > System."

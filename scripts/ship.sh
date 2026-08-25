#!/usr/bin/env bash
# One command for a whole round: fetch, patch, test, build, restart.
#
# Written because the assistant has no access to this machine - it can only hand over
# commands - and a four-line ssh chain with a backslash at every line end is a paste
# waiting to be mangled by a terminal.
#
# Usage, from the repository root:
#   ./scripts/ship.sh <patch-script.py> [more-scripts.py ...]
#   ./scripts/ship.sh --no-patch                 # just test + build + restart
#
# Order, and every step gates the next:
#   1. fetch the transport remote and take ONLY scripts/ from it (surgical - no merge)
#   2. run each patch script; any failure stops here, before anything is built
#   3. backend suite  (skipped when no Python changed)
#   4. frontend tsc + vitest  (skipped when no TS/TSX changed)
#   5. build, migrate, restart
#
# Nothing before step 5 touches the running containers.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "### 1/5 fetching scripts"
git fetch mirror dev
git checkout FETCH_HEAD -- scripts/
chmod +x scripts/*.sh

if [ "${1:-}" = "--no-patch" ]; then
  shift
else
  echo
  echo "### 2/5 applying"
  [ "$#" -gt 0 ] || { echo "no patch script named - pass one, or --no-patch" >&2; exit 2; }
  for script in "$@"; do
    [ -f "scripts/$script" ] || { echo "scripts/$script not found" >&2; exit 2; }
    echo "--- scripts/$script"
    python3 "scripts/$script"
  done
fi

# Only run the suite that can actually be affected. Running both every time turns a
# 10-second frontend change into a 4-minute wait and trains everyone to skip the gate.
changed=$(git status --porcelain -- backend frontend | awk '{print $NF}')
touched_backend=$(printf '%s\n' "$changed" | grep -c '^backend/' || true)
touched_frontend=$(printf '%s\n' "$changed" | grep -c '^frontend/' || true)

echo
if [ "$touched_backend" -gt 0 ]; then
  echo "### 3/5 backend suite ($touched_backend file(s) changed) - THE GATE"
  ./scripts/run-backend-tests.sh
else
  echo "### 3/5 backend untouched - suite skipped"
fi

echo
if [ "$touched_frontend" -gt 0 ]; then
  echo "### 4/5 frontend tsc + vitest ($touched_frontend file(s) changed) - THE GATE"
  ./scripts/run-frontend-tests.sh
else
  echo "### 4/5 frontend untouched - checks skipped"
fi

echo
echo "### 5/5 build, migrate, restart"
$COMPOSE build
$COMPOSE up -d db redis
$COMPOSE run --rm backend alembic upgrade head
$COMPOSE up -d
sleep 30
$COMPOSE ps

echo
echo "DONE. Nothing has been committed - review, then:"
echo "  git add -A backend frontend scripts && git commit -m '...' && git push origin dev"

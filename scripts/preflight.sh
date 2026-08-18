#!/usr/bin/env bash
# Dry-run the whole patch chain against a THROWAWAY copy of this working tree.
#
# Why this exists: these patches anchor on exact text in files that differ between
# branches, and the deployed tree is not something I can read from here. Each script
# already refuses to write anything unless every one of its anchors matches - which is
# safe, but it surfaces mismatches ONE PER DEPLOY. This surfaces all of them in a single
# run, against the real files, with zero risk to the real tree.
#
# It copies the working tree (source only - no .git, no node_modules, no build output)
# into /tmp, runs the chain there, and deletes it. Nothing in the repository is touched,
# no container is built, no migration runs.
#
# Usage, from the repository root:
#   bash scripts/preflight.sh
#
# Exit code is the chain's, so it gates a real deploy with &&:
#   bash scripts/preflight.sh && bash scripts/apply-decision-features.sh && ...
set -euo pipefail

cd "$(dirname "$0")/.."
[ -d backend/app ] || { echo "run from the repository root" >&2; exit 1; }

WORK="$(mktemp -d /tmp/prom-preflight.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

echo "==> copying the working tree to ${WORK} (source only)"
tar -cf - \
  --exclude=.git \
  --exclude=node_modules \
  --exclude=.next \
  --exclude=__pycache__ \
  --exclude=.venv \
  --exclude=venv \
  . | tar -C "$WORK" -xf -

echo "==> dry run: applying every patch to the COPY, not to your tree"
echo
cd "$WORK"
bash scripts/apply-decision-features.sh
status=$?

echo
if [ $status -eq 0 ]; then
  echo "PREFLIGHT PASSED - every patch applies cleanly to this tree."
  echo "The copy is now deleted; nothing in the repository was changed."
fi
exit $status

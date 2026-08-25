#!/usr/bin/env bash
# Type-check and unit-test the frontend, the way run-backend-tests.sh does for the API.
#
# Why this exists: the frontend has never had a gate outside `next build` inside the
# image build. That catches type errors eventually, but only after a ~70s image build,
# and it never runs vitest at all - so a broken test could sit green-looking forever.
#
# Dependencies live in the IMAGE at /app/node_modules; the source is mounted over /app
# and an anonymous volume keeps the image's node_modules from being shadowed by the
# mount. Nothing is written into the working tree.
#
# Usage:  ./scripts/run-frontend-tests.sh            # tsc + vitest
#         ./scripts/run-frontend-tests.sh -t nav     # args pass through to vitest
set -euo pipefail

cd "$(dirname "$0")/.."
[ -d frontend ] || { echo "frontend/ not found - run from the repository root" >&2; exit 1; }

IMAGE="prometheus-frontend-test:local"

echo "==> dependency image (cached after the first run)"
docker build -q -t "$IMAGE" -f - frontend >/dev/null <<'DOCKEREOF'
FROM node:20-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
DOCKEREOF

run() {
  docker run --rm \
    -v "$PWD/frontend:/app" -v /app/node_modules -v /app/.next \
    -w /app "$IMAGE" "$@"
}

echo "==> tsc --noEmit"
run npx tsc --noEmit

echo "==> vitest"
run npx vitest run "$@"

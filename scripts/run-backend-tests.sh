#!/usr/bin/env bash
# Run the backend test suite against a THROWAWAY Postgres.
#
# Why this exists: the repo has 36 backend test files that no deploy has ever run.
# The chain's only check was `python -c "import app.main"`, which catches an import
# error and nothing else - not a broken RBAC gate, not a route that started returning
# the wrong shape. These tests cover exactly that.
#
# Why it is not simply `pytest`: pytest lives in the `dev` extra and is deliberately
# absent from the production image, and conftest wants a real Postgres it is free to
# create and drop tables in. So this brings up its OWN database on a private network,
# runs the suite against that, and removes it afterwards. THE PRODUCTION DATABASE IS
# NEVER TOUCHED - it is not on the network the tests can see.
#
# Usage (from the repository root, on any host with Docker):
#   ./scripts/run-backend-tests.sh            # whole suite
#   ./scripts/run-backend-tests.sh -k rbac    # any pytest args pass straight through
#
# Exit code is pytest's, so it drops straight into a deploy chain with &&.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -d backend/tests ] || { echo "backend/tests not found - run from the repository root" >&2; exit 1; }

SUFFIX="$$"
NET="prom-test-net-${SUFFIX}"
PG="prom-test-pg-${SUFFIX}"
IMAGE="prometheus-backend-test:local"

cleanup() {
  docker rm -f "$PG" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> throwaway Postgres on a private network (production DB is not reachable from it)"
docker network create "$NET" >/dev/null
docker run -d --rm --name "$PG" --network "$NET" \
  -e POSTGRES_USER=prometheus -e POSTGRES_PASSWORD=prometheus -e POSTGRES_DB=prometheus_test \
  postgres:16-alpine >/dev/null

printf '    waiting for it'
for _ in $(seq 1 40); do
  if docker exec "$PG" pg_isready -U prometheus -d prometheus_test >/dev/null 2>&1; then
    echo " - ready"; break
  fi
  printf '.'; sleep 1
done
docker exec "$PG" pg_isready -U prometheus -d prometheus_test >/dev/null 2>&1 || {
  echo; echo "Postgres never became ready" >&2; exit 1; }

# The test image is the PRODUCTION image plus the dev extras, so the suite runs against
# the same dependency set that ships - not a separately resolved one that could pass
# here and fail in production.
echo "==> test image (production image + dev extras)"
docker build -q -t "$IMAGE" - >/dev/null <<'DOCKEREOF'
FROM prometheus-backend:latest
USER root
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov httpx
DOCKEREOF

echo "==> pytest"
# backend/ is mounted so tests/ (not copied into the image) is present, and so a
# failing run leaves nothing behind in the image.
docker run --rm --network "$NET" \
  -v "$PWD/backend:/src" -w /src \
  -e TEST_DATABASE_URL="postgresql+asyncpg://prometheus:prometheus@${PG}:5432/prometheus_test" \
  -e DATABASE_URL="postgresql+asyncpg://prometheus:prometheus@${PG}:5432/prometheus_test" \
  "$IMAGE" pytest -q "$@"

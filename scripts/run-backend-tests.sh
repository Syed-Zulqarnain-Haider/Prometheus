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
# create and drop tables in PLUS a real Redis (REDIS_TEST_URL - the rate limiter and
# cache tests exercise actual Redis semantics, not the FakeRedis used for auth). So
# this brings up its OWN Postgres and Redis on a private network, runs the suite
# against those, and removes them afterwards. PRODUCTION IS NEVER TOUCHED - neither
# the production database nor its Redis is on the network the tests can see.
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
RD="prom-test-redis-${SUFFIX}"
IMAGE="prometheus-backend-test:local"

cleanup() {
  docker rm -f "$PG" "$RD" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> throwaway Postgres + Redis on a private network (production is not reachable from it)"
docker network create "$NET" >/dev/null
docker run -d --rm --name "$PG" --network "$NET" \
  -e POSTGRES_USER=prometheus -e POSTGRES_PASSWORD=prometheus -e POSTGRES_DB=prometheus_test \
  postgres:16-alpine >/dev/null

docker run -d --rm --name "$RD" --network "$NET" redis:7-alpine >/dev/null

printf '    waiting for it'
for _ in $(seq 1 40); do
  if docker exec "$PG" pg_isready -U prometheus -d prometheus_test >/dev/null 2>&1; then
    echo " - ready"; break
  fi
  printf '.'; sleep 1
done
docker exec "$PG" pg_isready -U prometheus -d prometheus_test >/dev/null 2>&1 || {
  echo; echo "Postgres never became ready" >&2; exit 1; }
docker exec "$RD" redis-cli ping >/dev/null 2>&1 || {
  echo "Redis never became ready" >&2; exit 1; }

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
# The REPOSITORY ROOT is mounted, not just backend/: several tests resolve
# Path(__file__).parents[2] to reach the canonical <repo>/sync/metric_registry.py and
# compare it against the vendored backend/sync copy. Mounting only backend/ put those
# paths outside the container and produced eleven FileNotFoundError failures that said
# nothing about the code. Workdir is backend/ so pytest still collects from there.
docker run --rm --network "$NET" \
  -v "$PWD:/src" -w /src/backend \
  -e TEST_DATABASE_URL="postgresql+asyncpg://prometheus:prometheus@${PG}:5432/prometheus_test" \
  -e DATABASE_URL="postgresql+asyncpg://prometheus:prometheus@${PG}:5432/prometheus_test" \
  -e REDIS_TEST_URL="redis://${RD}:6379/0" \
  -e REDIS_URL="redis://${RD}:6379/0" \
  "$IMAGE" pytest -q "$@"

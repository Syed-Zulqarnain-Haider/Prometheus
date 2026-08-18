#!/usr/bin/env python3
"""Give the backend and frontend containers real healthchecks.

Postgres and Redis have had healthchecks all along; the two containers that actually
serve users had none. That is not academic - it bit this deployment: the backend
crash-looped on a bad import and `docker compose ps` reported "Up" the whole time,
so a deploy that had taken the API down looked like a success.

  backend   GET /health on the in-container port (8080). The python base image has no
            curl, so the probe uses urllib from the interpreter that is already there.
  frontend  GET /login. The node base image has no curl either; node 20 has global
            fetch. Anything under 500 counts as alive - a redirect still proves the
            server is answering.

The frontend's depends_on is upgraded from bare ordering to `condition:
service_healthy`. TRADE-OFF, stated plainly: `docker compose up -d` now FAILS LOUDLY
with "dependency failed to start" when the backend cannot become healthy, instead of
bringing up a frontend that greets everyone with "Couldn't load your account". The
cost is that a deploy with a broken backend brings up neither - which is the correct
outcome for a deploy, and does not affect an already-running stack (depends_on governs
startup only, never runtime).

Anchored: every anchor must appear EXACTLY once or nothing is written. Idempotent.
Takes effect on the next `docker compose up -d`; no migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

COMPOSE = Path("docker-compose.prod.yml")

BACKEND_ANCHOR = """    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
"""
BACKEND_NEW = """    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    # The python base image ships no curl; urllib is already in the interpreter.
    # start_period covers first boot (DB connect, cache warm) without counting as a
    # failure. A non-200 raises, which is exactly the signal we want.
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - import urllib.request;urllib.request.urlopen("http://127.0.0.1:8080/health",timeout=4)
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 40s
"""

FRONTEND_ANCHOR = """    ports:
      - "127.0.0.1:3000:3000"
    restart: unless-stopped
    depends_on:
      - backend
"""
FRONTEND_NEW = """    ports:
      - "127.0.0.1:3000:3000"
    restart: unless-stopped
    depends_on:
      # service_healthy, not bare ordering: a deploy whose backend cannot come up now
      # fails loudly instead of serving a dashboard that cannot reach its API.
      backend:
        condition: service_healthy
    # No curl in the node base image either; node 20 has global fetch. Under 500 counts
    # as alive - a redirect still proves the server is answering.
    healthcheck:
      test:
        - CMD
        - node
        - -e
        - fetch("http://127.0.0.1:3000/login").then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 20s
"""


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not COMPOSE.exists():
        die(f"{COMPOSE} not found - run from the repository root")

    text = COMPOSE.read_text()
    if "/health" in text and "healthcheck" in text.split("backend:")[-1][:1200]:
        print("already health-checked - nothing to do")
        return

    for anchor in (BACKEND_ANCHOR, FRONTEND_ANCHOR):
        if text.count(anchor) != 1:
            first = anchor.splitlines()[0].strip()
            die(f"{COMPOSE}: expected exactly one {first!r} block, found {text.count(anchor)}")

    text = text.replace(BACKEND_ANCHOR, BACKEND_NEW, 1)
    text = text.replace(FRONTEND_ANCHOR, FRONTEND_NEW, 1)
    COMPOSE.write_text(text)
    print(f"patched {COMPOSE}: backend + frontend healthchecks, frontend waits for a HEALTHY backend")
    print("\nVerify with: docker compose -f docker-compose.prod.yml ps")
    print("Both should report (healthy) once started.")


if __name__ == "__main__":
    main()

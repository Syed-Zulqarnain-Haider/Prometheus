#!/usr/bin/env python3
"""Two hardening fixes from the security audit, as anchored patches.

1. app/main.py    - disable /docs, /redoc and /openapi.json when ENV=production.
   Left on, they hand any caller the complete route inventory: admin endpoints,
   parameter names, response schemas, and the metric-group names RBAC is built on.

2. app/core/config.py + app/core/http.py - only believe X-Real-IP / X-Forwarded-For
   when TRUSTED_PROXY is set. client_ip() feeds the append-only audit_log, and that
   field is the one that says WHO did something. Reached directly (no nginx in front),
   any caller can currently stamp an arbitrary address on their own audit rows.
   Default is false: without a proxy we use the socket peer address, which cannot be
   forged. Set TRUSTED_PROXY=true in the environment for the nginx deployment.

Every anchor must appear EXACTLY once or nothing is written anywhere. Idempotent.
Restart the backend afterwards; no migration, no frontend rebuild.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAIN = Path("backend/app/main.py")
CONFIG = Path("backend/app/core/config.py")
HTTP = Path("backend/app/core/http.py")

# ── 1. docs off in production ────────────────────────────────────────────────
MAIN_ANCHOR = "app = FastAPI(title=settings.project_name, lifespan=lifespan)\n"
MAIN_REPLACEMENT = """app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
    # Interactive docs are a development tool. In production they hand any caller the
    # complete route inventory - admin endpoints, parameter names, response schemas,
    # the metric groups RBAC is built on - for free reconnaissance.
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)
"""

# ── 2. trusted-proxy setting ─────────────────────────────────────────────────
CONFIG_ANCHOR = "    sync_pg_dsn: str | None = None\n"
CONFIG_ADD = '''
    # Is a reverse proxy of OURS in front of this app, rewriting X-Real-IP /
    # X-Forwarded-For? Only then may those headers be believed. Default false:
    # reached directly, any caller could otherwise forge the client IP written into
    # the append-only audit_log. Set true on the nginx deployment.
    trusted_proxy: bool = False
'''

HTTP_IMPORT_ANCHOR = "from starlette.requests import Request\n"
HTTP_IMPORT_ADD = "\nfrom app.core.config import get_settings\n"

HTTP_BODY_ANCHOR = '''    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
'''
HTTP_BODY_REPLACEMENT = '''    # Header trust is OPT-IN. Both rules below assume our own proxy rewrote these
    # headers; reached directly, nothing does, and the caller picks their own audit
    # trail. The socket peer address cannot be forged, so that is the safe default.
    peer = request.client.host if request.client else None
    if not get_settings().trusted_proxy:
        return peer

    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
'''

HTTP_TAIL_ANCHOR = "    return request.client.host if request.client else None\n"
HTTP_TAIL_REPLACEMENT = "    return peer\n"


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def check(path: Path, anchors: list[str]) -> str:
    text = path.read_text()
    for anchor in anchors:
        if text.count(anchor) != 1:
            die(
                f"{path}: expected exactly one {anchor.splitlines()[0].strip()!r}, "
                f"found {text.count(anchor)} - the file has changed shape, patch by hand"
            )
    return text


def main() -> None:
    for path in (MAIN, CONFIG, HTTP):
        if not path.exists():
            die(f"{path} not found - run from the repository root")

    main_text = MAIN.read_text()
    config_text = CONFIG.read_text()
    http_text = HTTP.read_text()

    docs_done = "docs_url=None if _is_production" in main_text
    proxy_done = "trusted_proxy" in config_text and "trusted_proxy" in http_text

    if docs_done and proxy_done:
        print("already hardened - nothing to do")
        return

    # Validate EVERY anchor before writing ANY file, so a partial application is
    # impossible - half-patched auth code is worse than unpatched auth code.
    if not docs_done:
        if "_is_production" not in main_text:
            die(f"{MAIN}: no _is_production flag found - cannot gate the docs URLs")
        main_text = check(MAIN, [MAIN_ANCHOR])
    if not proxy_done:
        config_text = check(CONFIG, [CONFIG_ANCHOR])
        http_text = check(HTTP, [HTTP_IMPORT_ANCHOR, HTTP_BODY_ANCHOR, HTTP_TAIL_ANCHOR])

    if not docs_done:
        MAIN.write_text(main_text.replace(MAIN_ANCHOR, MAIN_REPLACEMENT, 1))
        print(f"patched {MAIN}: /docs, /redoc and /openapi.json off when ENV=production")
    if not proxy_done:
        CONFIG.write_text(config_text.replace(CONFIG_ANCHOR, CONFIG_ANCHOR + CONFIG_ADD, 1))
        http_text = http_text.replace(HTTP_IMPORT_ANCHOR, HTTP_IMPORT_ANCHOR + HTTP_IMPORT_ADD, 1)
        http_text = http_text.replace(HTTP_BODY_ANCHOR, HTTP_BODY_REPLACEMENT, 1)
        http_text = http_text.replace(HTTP_TAIL_ANCHOR, HTTP_TAIL_REPLACEMENT, 1)
        HTTP.write_text(http_text)
        print(f"patched {CONFIG} and {HTTP}: forwarded headers require TRUSTED_PROXY")

    print("\nIMPORTANT: this deployment runs behind nginx, so set TRUSTED_PROXY=true in the")
    print("backend environment - otherwise every audit row records the proxy's address")
    print("instead of the real client's. Then restart the backend (no migration needed).")


if __name__ == "__main__":
    main()

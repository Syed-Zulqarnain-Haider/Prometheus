"""FastAPI application entrypoint.

Wires CORS (exact origins from env), the standard error-envelope exception
handlers, and the liveness ``/health`` route. Business routes are mounted in
later build steps.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.middleware import audit_query_middleware
from app.api.v1 import admin as admin_routes
from app.api.v1 import apps as apps_routes
from app.api.v1 import auth as auth_routes
from app.api.v1 import export as export_routes
from app.api.v1 import layouts as layouts_routes
from app.api.v1 import meta as meta_routes
from app.api.v1 import metrics as metrics_routes
from app.api.v1 import reports as reports_routes
from app.api.v1 import views as views_routes
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.core.security_headers import build_security_headers_middleware
from app.services.cache_warm import warm_overview_cache
from app.services.sync_scheduler import scheduler_loop

logger = logging.getLogger("app.main")

settings = get_settings()
_is_production = settings.env.lower() in ("production", "prod")
_is_test = settings.env.lower() in ("test", "testing")

# Fail loudly (in logs) on a misconfigured prod deploy rather than silently
# serving with no allowed origins — every browser request would then break.
if _is_production and not settings.cors_origin_list:
    logger.error("CORS_ORIGINS is empty in production — the frontend will be blocked.")


def _check_pooled_db_endpoint() -> None:
    """Nudge toward Neon's POOLED endpoint for lower per-request connect latency.

    Neon's pooled host carries a ``-pooler`` segment. A direct (non-pooled) host
    pays a fresh connection handshake per request — costly against a free-tier DB
    that also cold-starts. We only warn (never fail): the URL is env/secret-provided.
    """
    url = settings.database_url
    if "neon.tech" in url and "-pooler" not in url:
        logger.warning(
            "DATABASE_URL points at a Neon host without '-pooler' — use the POOLED "
            "endpoint (host contains '-pooler') for lower per-request connection latency."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: nudge DB config and warm the aggregate cache in the background.

    Warm-up is fire-and-forget so it never delays readiness, and idempotent so a
    cold instance (or a run right after the daily cache bust) repopulates the
    default Overview without blocking the first real request. Skipped under tests.
    """
    _check_pooled_db_endpoint()
    if not _is_test:

        async def _warm() -> None:
            try:
                await warm_overview_cache(app.state.sessionmaker, redis_client)
            except Exception:  # noqa: BLE001 — warm-up is best-effort, never fatal
                logger.exception("aggregate cache warm-up failed")

        app.state.warm_task = asyncio.create_task(_warm())
        # Daily-sync scheduler: safe on every instance (advisory-lock guarded). It only
        # acts when an admin enables the sync and the configured time is reached.
        app.state.scheduler_task = asyncio.create_task(
            scheduler_loop(app.state.sessionmaker, settings)
        )
    yield
    scheduler_task = getattr(app.state, "scheduler_task", None)
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


app = FastAPI(title=settings.project_name, lifespan=lifespan)

# Session factory used by the audit middleware (overridable in tests).
app.state.sessionmaker = AsyncSessionLocal

# Security headers on every response (HSTS only in production, where TLS exists).
app.middleware("http")(build_security_headers_middleware(enable_hsts=_is_production))

# Audit api_query for data routes (added before CORS so it wraps the response).
app.middleware("http")(audit_query_middleware)

# CORS: exact frontend origins only (never "*"); configured via env.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(
    code: str,
    message: str,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the canonical error envelope: ``{"error": {"code", "message"}}``."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


# Map common HTTP status codes to stable, client-facing error codes.
_STATUS_CODE_MAP: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Render HTTP errors in the error envelope (no internals leaked)."""
    code = _STATUS_CODE_MAP.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    # Preserve headers (e.g. Retry-After on 429).
    headers = dict(exc.headers) if exc.headers else None
    return _error_response(code, message, exc.status_code, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a generic validation error — never echo raw input or internals."""
    return _error_response("validation_error", "Request validation failed.", 422)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: never expose stack traces or SQL to clients."""
    return _error_response("internal_error", "An unexpected error occurred.", 500)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness probe. Does not touch external dependencies."""
    return {"status": "ok"}


app.include_router(auth_routes.router, prefix=settings.api_v1_prefix)
app.include_router(auth_routes.public_router, prefix=settings.api_v1_prefix)
app.include_router(metrics_routes.router, prefix=settings.api_v1_prefix)
app.include_router(apps_routes.router, prefix=settings.api_v1_prefix)
app.include_router(meta_routes.router, prefix=settings.api_v1_prefix)
app.include_router(views_routes.router, prefix=settings.api_v1_prefix)
app.include_router(layouts_routes.router, prefix=settings.api_v1_prefix)
app.include_router(reports_routes.router, prefix=settings.api_v1_prefix)
app.include_router(export_routes.router, prefix=settings.api_v1_prefix)
app.include_router(admin_routes.router, prefix=settings.api_v1_prefix)

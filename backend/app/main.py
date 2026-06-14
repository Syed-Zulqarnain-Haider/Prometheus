"""FastAPI application entrypoint.

Wires CORS (exact origins from env), the standard error-envelope exception
handlers, and the liveness ``/health`` route. Business routes are mounted in
later build steps.
"""

from __future__ import annotations

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
from app.api.v1 import meta as meta_routes
from app.api.v1 import metrics as metrics_routes
from app.api.v1 import reports as reports_routes
from app.api.v1 import views as views_routes
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal

settings = get_settings()

app = FastAPI(title=settings.project_name)

# Session factory used by the audit middleware (overridable in tests).
app.state.sessionmaker = AsyncSessionLocal

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
app.include_router(metrics_routes.router, prefix=settings.api_v1_prefix)
app.include_router(apps_routes.router, prefix=settings.api_v1_prefix)
app.include_router(meta_routes.router, prefix=settings.api_v1_prefix)
app.include_router(views_routes.router, prefix=settings.api_v1_prefix)
app.include_router(reports_routes.router, prefix=settings.api_v1_prefix)
app.include_router(export_routes.router, prefix=settings.api_v1_prefix)
app.include_router(admin_routes.router, prefix=settings.api_v1_prefix)

"""Observability: request tracing, structured logging, and optional Sentry.

Three pieces, all safe to run everywhere and all no-ops when unconfigured:

  * a per-request trace id (``X-Request-ID``, honored from the edge or generated) carried on a
    ContextVar so EVERY log line for a request is correlatable, and echoed back on the response
    so a user can quote it to support;
  * structured logs (JSON in prod, plain text locally) that always include the trace id;
  * Sentry error reporting, enabled only when ``SENTRY_DSN`` is set (lazy import, PII off).

Nothing here changes behavior when secrets are absent — the trace id still flows, logs still
emit, and Sentry simply stays off.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings

REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

log = logging.getLogger("app.request")

# Whether Sentry actually initialized (so capture_exception can short-circuit cheaply).
_sentry_on = False


def get_request_id() -> str:
    """The current request's trace id, or '-' outside a request."""
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


class _RequestIdFilter(logging.Filter):
    """Attach the current trace id to every record so formatters can include it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class _JsonFormatter(logging.Formatter):
    """Compact single-line JSON — friendly to log aggregators (Cloud Logging, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Install the trace-id filter + formatter on the root handler. Idempotent."""
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    handler: logging.Handler
    if root.handlers:
        handler = root.handlers[0]
    else:
        handler = logging.StreamHandler()
        root.addHandler(handler)

    # Reset our filter (avoid duplicates on re-init) and pick the formatter by env.
    handler.filters = [f for f in handler.filters if not isinstance(f, _RequestIdFilter)]
    handler.addFilter(_RequestIdFilter())
    if settings.log_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )


def init_sentry(settings: Settings) -> bool:
    """Initialize Sentry iff SENTRY_DSN is set. Returns True when active. Never raises."""
    global _sentry_on
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,  # never ship user PII to the error tracker
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        _sentry_on = True
        log.info("Sentry error reporting enabled")
    except Exception:  # noqa: BLE001 — observability must never break startup
        log.exception("Sentry init failed; continuing without it")
        _sentry_on = False
    return _sentry_on


def capture_exception(exc: BaseException) -> None:
    """Report an exception to Sentry when active; a cheap no-op otherwise."""
    if not _sentry_on:
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001 — reporting must never raise into the request path
        log.exception("Sentry capture failed")


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign/propagate a trace id, time the request, and emit one structured access log.

    The id comes from the edge's ``X-Request-ID`` if present (so a trace spans the edge and the
    app), else a fresh UUID. It is stored on ``request.state`` and a ContextVar, and echoed on
    the response. ``/health`` is skipped to keep probe noise out of the logs.
    """
    incoming = request.headers.get(REQUEST_ID_HEADER)
    rid = incoming if incoming and len(incoming) <= 64 else uuid.uuid4().hex
    set_request_id(rid)
    request.state.request_id = rid

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 — log + report, then re-raise to the handlers
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        log.exception(
            "request failed: %s %s (%.1fms)", request.method, request.url.path, elapsed_ms
        )
        capture_exception(exc)
        raise
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers[REQUEST_ID_HEADER] = rid
    if request.url.path != "/health":
        log.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    return response

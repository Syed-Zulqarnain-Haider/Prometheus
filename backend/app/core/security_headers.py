"""Security response headers applied to every response.

A small, framework-level hardening layer: it makes the JSON API un-embeddable and
un-sniffable, and (in production, where TLS is terminated by Cloud Run) asserts HSTS.
These complement — never replace — the server-side RBAC and the locked CORS policy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

# Static headers safe for an all-JSON API consumed cross-origin via fetch.
_BASE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # The API never returns HTML; lock everything down and forbid framing.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}

# Sent only in production (Cloud Run serves over HTTPS); harmless if a browser
# sees it over http, but we avoid asserting it in local dev.
_HSTS_HEADER = ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


def build_security_headers_middleware(
    *, enable_hsts: bool
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Return an HTTP middleware that stamps security headers on every response."""

    async def security_headers_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for key, value in _BASE_HEADERS.items():
            response.headers.setdefault(key, value)
        if enable_hsts:
            response.headers.setdefault(_HSTS_HEADER[0], _HSTS_HEADER[1])
        return response

    return security_headers_middleware

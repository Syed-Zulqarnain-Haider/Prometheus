"""Small HTTP request helpers."""

from __future__ import annotations

from starlette.requests import Request


def client_ip(request: Request) -> str | None:
    """Best-effort client IP, honoring a single X-Forwarded-For hop from the edge."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None

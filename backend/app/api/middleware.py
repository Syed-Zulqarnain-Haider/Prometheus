"""HTTP middleware: audit-log ``api_query`` events for data routes.

After a successful response to a data route, append an ``api_query`` audit entry
capturing who queried what, with which filters. The authenticated user context is
stashed on ``request.state.user_context`` by the auth dependency; the session
factory is read from ``request.app.state.sessionmaker``. Like the audit service,
this never raises into the request path.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from app.core.http import client_ip
from app.services.audit import AuditService

logger = logging.getLogger("app.api.middleware")

# Routes that serve scoped fact data — an access to these is an "api_query".
DATA_ROUTE_PREFIXES: tuple[str, ...] = ("/api/v1/metrics", "/api/v1/apps")


def is_data_route(path: str) -> bool:
    return path.startswith(DATA_ROUTE_PREFIXES)


async def audit_query_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log api_query for successful, authenticated data-route requests."""
    response = await call_next(request)
    try:
        if response.status_code < 400 and is_data_route(request.url.path):
            user_context = getattr(request.state, "user_context", None)
            sessionmaker = getattr(request.app.state, "sessionmaker", None)
            if user_context is not None and sessionmaker is not None:
                await AuditService(sessionmaker).write(
                    user_id=user_context.user_id,
                    action="api_query",
                    resource=request.url.path,
                    detail={
                        "method": request.method,
                        "query": dict(request.query_params),
                        "status_code": response.status_code,
                    },
                    ip=client_ip(request),
                    user_agent=request.headers.get("user-agent"),
                )
    except Exception:
        # Belt-and-suspenders: never let auditing break a request.
        logger.exception("Audit middleware failed for %s", request.url.path)
    return response

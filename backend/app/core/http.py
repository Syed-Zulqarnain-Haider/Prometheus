"""Small HTTP request helpers."""

from __future__ import annotations

from starlette.requests import Request


def client_ip(request: Request) -> str | None:
    """Client IP as our own edge saw it — not as the caller claims it is.

    This value is written into the append-only ``audit_log``, so it has to be one the
    caller cannot choose. Two headers arrive and only one of them is trustworthy:

    * ``X-Real-IP`` — nginx sets it from ``$remote_addr`` with ``proxy_set_header``, which
      OVERWRITES anything the client sent. Trustworthy.
    * ``X-Forwarded-For`` — nginx builds it with ``proxy_add_x_forwarded_for``, which
      APPENDS the real address to whatever the client supplied. So the FIRST entry is
      attacker-controlled and the LAST is the one our proxy added.

    Reading ``X-Forwarded-For[0]`` therefore let any caller stamp an arbitrary address on
    every audit row simply by sending the header — forging the one field that says who did
    something. We prefer ``X-Real-IP`` and fall back to the last forwarded hop.

    NOTE: "last hop" is correct for exactly one reverse proxy, which is what
    ``docs/nginx-prometheus.conf`` deploys. Putting a CDN in front (Cloudflare and the
    like) would make the last hop the CDN's address; that setup needs an explicit
    trusted-proxy count instead of this rule.
    """
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]

    return request.client.host if request.client else None

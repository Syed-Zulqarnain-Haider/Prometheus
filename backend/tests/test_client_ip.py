"""``client_ip`` must report what our own edge saw, never what the caller claims.

The value lands in the append-only ``audit_log``. A caller who can choose it can forge the
one field that says where an action came from.
"""

from __future__ import annotations

from app.core.http import client_ip
from starlette.requests import Request


def _request(headers: dict[str, str], peer: str | None = "10.0.0.9") -> Request:
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    if peer is not None:
        scope["client"] = (peer, 51234)
    return Request(scope)  # type: ignore[arg-type]


def test_prefers_x_real_ip() -> None:
    # nginx overwrites X-Real-IP with $remote_addr, so it is the trustworthy one.
    assert client_ip(_request({"X-Real-IP": "203.0.113.7"})) == "203.0.113.7"


def test_spoofed_forwarded_for_is_ignored_when_real_ip_present() -> None:
    got = client_ip(
        _request({"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "1.2.3.4, 203.0.113.7"})
    )
    assert got == "203.0.113.7"


def test_takes_the_last_forwarded_hop_not_the_first() -> None:
    # proxy_add_x_forwarded_for APPENDS the real address, so a client that sends
    # "X-Forwarded-For: 1.2.3.4" produces "1.2.3.4, <real>". The last hop is ours.
    assert client_ip(_request({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})) == "203.0.113.7"


def test_single_forwarded_hop() -> None:
    assert client_ip(_request({"X-Forwarded-For": "203.0.113.7"})) == "203.0.113.7"


def test_blank_and_whitespace_headers_fall_through_to_the_socket() -> None:
    assert client_ip(_request({"X-Real-IP": "   "})) == "10.0.0.9"
    assert client_ip(_request({"X-Forwarded-For": " , "})) == "10.0.0.9"


def test_no_headers_uses_the_socket_peer() -> None:
    assert client_ip(_request({})) == "10.0.0.9"


def test_no_client_and_no_headers_is_none() -> None:
    assert client_ip(_request({}, peer=None)) is None

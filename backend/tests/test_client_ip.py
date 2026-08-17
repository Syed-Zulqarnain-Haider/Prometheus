"""``client_ip`` must report what our own edge saw, never what the caller claims.

The value lands in the append-only ``audit_log``. A caller who can choose it can forge the
one field that says where an action came from.

Header trust is OPT-IN via ``TRUSTED_PROXY``. Both halves are tested here, because each
one is a separate security property:

* ``TRUSTED_PROXY=false`` (the default): the headers are attacker-controlled and must be
  ignored entirely in favour of the socket peer, which cannot be forged.
* ``TRUSTED_PROXY=true``: our own nginx rewrote them, so ``X-Real-IP`` wins and the LAST
  ``X-Forwarded-For`` hop - the one our proxy appended - is the real client.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.core.config import get_settings
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


@pytest.fixture
def trusted_proxy(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run the body with header trust ON.

    ``get_settings`` is ``lru_cache``d, so the cache has to be cleared on the way in AND
    on the way out - otherwise a cached Settings leaks the override into other tests.
    """
    monkeypatch.setenv("TRUSTED_PROXY", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _untrusted_by_default(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Default every test to header trust OFF, independent of the ambient environment."""
    monkeypatch.setenv("TRUSTED_PROXY", "false")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    get_settings.cache_clear()


# ---- TRUSTED_PROXY=false: headers are worthless and must be ignored ----------------


def test_untrusted_ignores_x_real_ip() -> None:
    # Reached directly, nothing overwrote this header - so believing it would let the
    # caller choose the IP recorded against their own actions.
    assert client_ip(_request({"X-Real-IP": "203.0.113.7"})) == "10.0.0.9"


def test_untrusted_ignores_forwarded_for() -> None:
    assert client_ip(_request({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})) == "10.0.0.9"


def test_untrusted_ignores_both_headers_together() -> None:
    got = client_ip(
        _request({"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "1.2.3.4, 203.0.113.7"})
    )
    assert got == "10.0.0.9"


def test_untrusted_with_no_client_is_none() -> None:
    # No socket peer and no trustworthy header: report nothing rather than a forgeable value.
    assert client_ip(_request({"X-Real-IP": "203.0.113.7"}, peer=None)) is None


# ---- TRUSTED_PROXY=true: our nginx rewrote the headers ----------------------------


@pytest.mark.usefixtures("trusted_proxy")
def test_prefers_x_real_ip() -> None:
    # nginx overwrites X-Real-IP with $remote_addr, so it is the trustworthy one.
    assert client_ip(_request({"X-Real-IP": "203.0.113.7"})) == "203.0.113.7"


@pytest.mark.usefixtures("trusted_proxy")
def test_spoofed_forwarded_for_is_ignored_when_real_ip_present() -> None:
    got = client_ip(
        _request({"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "1.2.3.4, 203.0.113.7"})
    )
    assert got == "203.0.113.7"


@pytest.mark.usefixtures("trusted_proxy")
def test_takes_the_last_forwarded_hop_not_the_first() -> None:
    # proxy_add_x_forwarded_for APPENDS the real address, so a client that sends
    # "X-Forwarded-For: 1.2.3.4" produces "1.2.3.4, <real>". The last hop is ours.
    assert client_ip(_request({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})) == "203.0.113.7"


@pytest.mark.usefixtures("trusted_proxy")
def test_single_forwarded_hop() -> None:
    assert client_ip(_request({"X-Forwarded-For": "203.0.113.7"})) == "203.0.113.7"


@pytest.mark.usefixtures("trusted_proxy")
def test_blank_and_whitespace_headers_fall_through_to_the_socket() -> None:
    assert client_ip(_request({"X-Real-IP": "   "})) == "10.0.0.9"
    assert client_ip(_request({"X-Forwarded-For": " , "})) == "10.0.0.9"


@pytest.mark.usefixtures("trusted_proxy")
def test_no_headers_uses_the_socket_peer() -> None:
    assert client_ip(_request({})) == "10.0.0.9"


@pytest.mark.usefixtures("trusted_proxy")
def test_no_client_and_no_headers_is_none() -> None:
    assert client_ip(_request({}, peer=None)) is None

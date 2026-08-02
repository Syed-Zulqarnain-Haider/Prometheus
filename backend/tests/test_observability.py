"""Request tracing, error-envelope trace ids, and Sentry gating."""

from __future__ import annotations

from app.core import observability
from app.core.config import get_settings

from tests.conftest import MetricsEnv


async def test_health_response_carries_a_trace_id(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")


async def test_incoming_trace_id_is_propagated(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.headers.get("X-Request-ID") == "trace-abc-123"


async def test_error_envelope_includes_request_id(metrics_env: MetricsEnv) -> None:
    # Unauthenticated call → 401 in the standard envelope, now with a quotable trace id.
    resp = await metrics_env.client.get(
        "/api/v1/metrics/summary?date_from=2026-06-01&date_to=2026-06-02"
    )
    assert resp.status_code == 401
    body = resp.json()
    assert set(body["error"]) >= {"code", "message", "request_id"}
    # The id in the body matches the response header.
    assert body["error"]["request_id"] == resp.headers.get("X-Request-ID")


def test_sentry_stays_off_without_dsn() -> None:
    settings = get_settings()  # test env has no SENTRY_DSN
    assert observability.init_sentry(settings) is False
    # capture is a safe no-op when Sentry is off.
    observability.capture_exception(RuntimeError("boom"))


def test_logging_configures_without_error() -> None:
    observability.configure_logging(get_settings())  # idempotent, must not raise
    assert observability.get_request_id()  # returns a value ('-' outside a request)

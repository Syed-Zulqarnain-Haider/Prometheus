"""Smoke tests for the app entrypoint: health route and error envelope."""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_route_uses_error_envelope():
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == "not_found"


def test_security_headers_present():
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    # HSTS is asserted only in production (TLS), and tests run with ENV=test.
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_enabled_when_requested():
    from app.core.security_headers import build_security_headers_middleware
    from fastapi import FastAPI

    prod_app = FastAPI()
    prod_app.middleware("http")(build_security_headers_middleware(enable_hsts=True))

    @prod_app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    response = TestClient(prod_app).get("/ping")
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["X-Frame-Options"] == "DENY"

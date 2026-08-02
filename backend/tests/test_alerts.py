"""Proactive anomaly alerts."""

from datetime import date, timedelta
from typing import Any

import pytest
from app.core.fact_table import FACT_TABLE
from app.services import email_service
from sqlalchemy import insert

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _enable_alerts(env: MetricsEnv) -> None:
    resp = await env.client.put(
        "/api/v1/admin/settings/alerts_enabled", json={"value": True}, headers=_auth("admin")
    )
    assert resp.status_code == 200


async def _seed_two_days(env: MetricsEnv, rev_prev: float, rev_now: float, spend: float) -> None:
    today = date.today()
    yday = today - timedelta(days=1)
    async with env.sessionmaker() as s:
        await s.execute(
            insert(FACT_TABLE),
            [
                {
                    "date": yday,
                    "platform": "ios",
                    "canonical_key": "zz",
                    "total_revenue_usd": rev_prev,
                    "total_ua_spend_usd": spend,
                },
                {
                    "date": today,
                    "platform": "ios",
                    "canonical_key": "zz",
                    "total_revenue_usd": rev_now,
                    "total_ua_spend_usd": spend,
                },
            ],
        )
        await s.commit()


async def test_alerts_disabled_is_noop(metrics_env: MetricsEnv) -> None:
    """Off by default → evaluate returns nothing (never a surprise alert on a fresh deploy)."""
    resp = await metrics_env.client.post("/api/v1/admin/alerts/evaluate", headers=_auth("admin"))
    assert resp.status_code == 200
    assert resp.json() == {"count": 0, "fired": []}


async def test_alerts_require_admin(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post("/api/v1/admin/alerts/evaluate", headers=_auth("viewer"))
    assert resp.status_code in (403, 404)


async def test_revenue_drop_fires_and_emails_admins(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1000 -> 300 = 70% drop; spend flat so no spike; ROAS 3.0x so no low-roas.
    await _seed_two_days(metrics_env, rev_prev=1000, rev_now=300, spend=100)
    await _enable_alerts(metrics_env)

    sent: list[str] = []

    async def fake_send(settings: Any, recipients: list[str], subject: str, body: str) -> bool:
        sent.append(subject)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)

    resp = await metrics_env.client.post("/api/v1/admin/alerts/evaluate", headers=_auth("admin"))
    assert resp.status_code == 200
    keys = {a["key"] for a in resp.json()["fired"]}
    assert "revenue_drop" in keys
    assert "spend_spike" not in keys and "low_roas" not in keys
    assert sent, "admins should have been emailed the alert digest"


async def _enable(env: MetricsEnv, key: str) -> None:
    resp = await env.client.put(
        f"/api/v1/admin/settings/{key}", json={"value": True}, headers=_auth("admin")
    )
    assert resp.status_code == 200


async def test_digest_disabled_is_noop(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post("/api/v1/admin/digest/send", headers=_auth("admin"))
    assert resp.status_code == 200
    assert resp.json() == {"sent": False, "preview": None}


async def test_digest_sends_when_enabled(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_two_days(metrics_env, rev_prev=800, rev_now=1000, spend=200)
    await _enable(metrics_env, "digest_enabled")

    sent: list[str] = []

    async def fake_send(settings: Any, recipients: list[str], subject: str, body: str) -> bool:
        sent.append(subject)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)

    resp = await metrics_env.client.post("/api/v1/admin/digest/send", headers=_auth("admin"))
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["sent"] is True
    assert "digest" in payload["preview"].lower()
    assert sent, "admins should have been emailed the digest"


async def test_low_roas_fires(metrics_env: MetricsEnv) -> None:
    # Latest day ROAS = 50/100 = 0.5x, below the default 1.0x floor.
    await _seed_two_days(metrics_env, rev_prev=90, rev_now=50, spend=100)
    await _enable_alerts(metrics_env)

    resp = await metrics_env.client.post("/api/v1/admin/alerts/evaluate", headers=_auth("admin"))
    assert resp.status_code == 200
    assert "low_roas" in {a["key"] for a in resp.json()["fired"]}

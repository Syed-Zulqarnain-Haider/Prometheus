"""Scheduled report delivery: CRUD, ownership, RBAC-safe delivery, and the due/claim logic."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from app.models import ReportSchedule
from app.services import email_service, report_delivery_service
from sqlalchemy import select

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _make_report(env: MetricsEnv, role: str) -> str:
    body = {
        "name": "Revenue by app",
        "filters": {"date_from": "2026-06-01", "date_to": "2026-06-30"},
        "columns": ["total_revenue_usd"],
        "group_by": "app",
    }
    resp = await env.client.post("/api/v1/reports", json=body, headers=_auth(role))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_create_list_delete_schedule(metrics_env: MetricsEnv) -> None:
    report_id = await _make_report(metrics_env, "admin")
    create = await metrics_env.client.post(
        f"/api/v1/reports/{report_id}/schedules",
        json={"cadence": "daily", "hour": 6, "fmt": "xlsx"},
        headers=_auth("admin"),
    )
    assert create.status_code == 201, create.text
    schedule_id = create.json()["id"]

    listed = await metrics_env.client.get(
        f"/api/v1/reports/{report_id}/schedules", headers=_auth("admin")
    )
    assert [s["id"] for s in listed.json()] == [schedule_id]

    deleted = await metrics_env.client.delete(
        f"/api/v1/reports/schedules/{schedule_id}", headers=_auth("admin")
    )
    assert deleted.status_code == 204
    again = await metrics_env.client.get(
        f"/api/v1/reports/{report_id}/schedules", headers=_auth("admin")
    )
    assert again.json() == []


async def test_weekly_requires_day_of_week(metrics_env: MetricsEnv) -> None:
    report_id = await _make_report(metrics_env, "admin")
    resp = await metrics_env.client.post(
        f"/api/v1/reports/{report_id}/schedules",
        json={"cadence": "weekly", "hour": 6},  # missing day_of_week
        headers=_auth("admin"),
    )
    assert resp.status_code == 422


async def test_cannot_schedule_another_users_report(metrics_env: MetricsEnv) -> None:
    report_id = await _make_report(metrics_env, "admin")
    # A different user must not be able to schedule the admin's report → 404 (not 403).
    resp = await metrics_env.client.post(
        f"/api/v1/reports/{report_id}/schedules",
        json={"cadence": "daily", "hour": 6},
        headers=_auth("executive"),
    )
    assert resp.status_code == 404


async def test_run_now_emails_only_the_owner(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_id = await _make_report(metrics_env, "admin")
    create = await metrics_env.client.post(
        f"/api/v1/reports/{report_id}/schedules",
        json={"cadence": "daily", "hour": 6, "fmt": "csv"},
        headers=_auth("admin"),
    )
    schedule_id = create.json()["id"]

    captured: list[tuple[list[str], Any]] = []

    async def fake_send(settings: Any, recipients: list[str], subject: str, body: str, **kw: Any):
        captured.append((recipients, kw.get("attachments")))
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)

    resp = await metrics_env.client.post(
        f"/api/v1/reports/schedules/{schedule_id}/run-now", headers=_auth("admin")
    )
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert len(captured) == 1
    recipients, attachments = captured[0]
    # Delivered ONLY to the owner (never to anyone else) — the RBAC-safe delivery guarantee.
    assert recipients == ["admin-uid@terafort.org"]
    assert attachments and attachments[0].filename.endswith(".csv")


# ── unit: due + rolling window + claim ───────────────────────────────────────
def _sched(**kw: Any) -> ReportSchedule:
    defaults: dict[str, Any] = {
        "cadence": "daily",
        "hour": 9,
        "day_of_week": None,
        "day_of_month": None,
        "timezone": "UTC",
        "enabled": True,
        "last_run_on": None,
    }
    return ReportSchedule(**{**defaults, **kw})


def test_is_due_daily() -> None:
    at_9 = datetime(2026, 6, 15, 9, 30, tzinfo=UTC)
    assert report_delivery_service.is_due(_sched(hour=9), at_9)
    assert not report_delivery_service.is_due(_sched(hour=10), at_9)
    # Already delivered today → not due again.
    assert not report_delivery_service.is_due(_sched(hour=9, last_run_on=date(2026, 6, 15)), at_9)
    # Disabled → never due.
    assert not report_delivery_service.is_due(_sched(hour=9, enabled=False), at_9)


def test_is_due_weekly_and_monthly() -> None:
    # 2026-06-15 is a Monday (weekday 0).
    monday_9 = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    assert report_delivery_service.is_due(_sched(cadence="weekly", day_of_week=0), monday_9)
    assert not report_delivery_service.is_due(_sched(cadence="weekly", day_of_week=2), monday_9)
    assert report_delivery_service.is_due(_sched(cadence="monthly", day_of_month=15), monday_9)
    assert not report_delivery_service.is_due(_sched(cadence="monthly", day_of_month=16), monday_9)


def test_rolled_filters_preserves_span() -> None:
    rolled = report_delivery_service._rolled_filters(
        {"date_from": "2026-06-01", "date_to": "2026-06-30", "platform": "ios"},
        date(2026, 8, 2),
    )
    assert rolled["date_to"] == "2026-08-02"
    assert rolled["date_from"] == "2026-07-04"  # 29-day span preserved
    assert rolled["platform"] == "ios"  # other filters untouched


async def test_evaluate_due_delivers_once_then_claims(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _make_report(metrics_env, "admin")
    now = datetime.now(UTC)
    # Delivery only runs when a mail transport is configured; set one for this test.
    settings = get_test_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.local")
    monkeypatch.setattr(settings, "smtp_from", "prometheus@terafort.org")
    # A schedule due right now (this UTC hour), not yet run.
    from app.models import SavedReport

    async with metrics_env.sessionmaker() as s:
        report = await s.scalar(select(SavedReport).where(SavedReport.name == "Revenue by app"))
        assert report is not None
        s.add(
            ReportSchedule(
                report_id=report.id,
                user_id=report.user_id,
                cadence="daily",
                hour=now.hour,
                timezone="UTC",
                enabled=True,
            )
        )
        await s.commit()

    sends: list[list[str]] = []

    async def fake_send(settings: Any, recipients: list[str], subject: str, body: str, **kw: Any):
        sends.append(recipients)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)

    delivered = await report_delivery_service.evaluate_due(
        metrics_env.sessionmaker, get_test_settings(), now
    )
    assert delivered == 1
    assert sends == [["admin-uid@terafort.org"]]

    # Second run in the same day is a no-op (claimed via last_run_on).
    delivered_again = await report_delivery_service.evaluate_due(
        metrics_env.sessionmaker, get_test_settings(), now + timedelta(minutes=1)
    )
    assert delivered_again == 0


def get_test_settings() -> Any:
    from app.core.config import get_settings

    return get_settings()

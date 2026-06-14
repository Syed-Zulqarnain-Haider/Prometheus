"""Integration tests for Step 6 exports.

Covers the capability gate, CSV/XLSX output, the not-enabled Google Sheets path,
the export-specific rate limit, and the audit trail.
"""

from typing import Any

from app.models import AuditLog
from sqlalchemy import func, select

from tests.conftest import MetricsEnv

RANGE: dict[str, Any] = {"date_from": "2026-06-01", "date_to": "2026-06-02"}


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def _adhoc(fmt: str) -> dict[str, Any]:
    return {
        "format": fmt,
        "filters": dict(RANGE),
        "columns": ["store_total_installs", "total_revenue_usd"],
        "group_by": "app",
    }


async def test_viewer_cannot_export(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        "/api/v1/export", json=_adhoc("csv"), headers=_auth("viewer")
    )
    assert resp.status_code == 403


async def test_csv_export(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        "/api/v1/export", json=_adhoc("csv"), headers=_auth("admin")
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.text
    assert "store_total_installs" in body.splitlines()[0]
    assert "appA" in body


async def test_xlsx_export(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        "/api/v1/export", json=_adhoc("xlsx"), headers=_auth("admin")
    )
    assert resp.status_code == 200
    assert "openxmlformats" in resp.headers["content-type"]
    # XLSX files are zip archives — they start with the PK magic bytes.
    assert resp.content[:2] == b"PK"


async def test_gsheet_not_enabled(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        "/api/v1/export", json=_adhoc("gsheet"), headers=_auth("admin")
    )
    assert resp.status_code == 501


async def test_export_is_audited(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.post("/api/v1/export", json=_adhoc("csv"), headers=_auth("admin"))
    async with metrics_env.sessionmaker() as session:
        count = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "export")
        )
    assert count == 1


async def test_export_rate_limited(metrics_env: MetricsEnv) -> None:
    client = metrics_env.client
    # 10/min export budget: the 11th call is rejected with 429.
    for _ in range(10):
        ok = await client.post("/api/v1/export", json=_adhoc("csv"), headers=_auth("finance"))
        assert ok.status_code == 200
    blocked = await client.post("/api/v1/export", json=_adhoc("csv"), headers=_auth("finance"))
    assert blocked.status_code == 429

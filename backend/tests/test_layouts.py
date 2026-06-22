"""Integration tests for per-user dashboard layout persistence.

Covers: auth required, page validation, default fallback, save→load round-trip,
reset, strict per-user isolation (one user never sees/overwrites another's), and
that save/reset are audited.
"""

from typing import Any

from app.models import AuditLog
from sqlalchemy import select

from tests.conftest import MetricsEnv

PAGE = "/api/v1/dashboard-layouts/overview"


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def _layout(seed: int) -> dict[str, Any]:
    return {"lg": [{"i": "trend", "x": 0, "y": seed, "w": 6, "h": 10}]}


async def test_requires_auth(metrics_env: MetricsEnv) -> None:
    assert (await metrics_env.client.get(PAGE)).status_code == 401
    assert (await metrics_env.client.put(PAGE, json={"layout": _layout(0)})).status_code == 401


async def test_unknown_page_is_404(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(
        "/api/v1/dashboard-layouts/not-a-page", headers=_auth("admin")
    )
    assert resp.status_code == 404


async def test_default_fallback_when_unsaved(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(PAGE, headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == "overview"
    assert body["layout"] is None  # client falls back to its default arrangement
    assert body["updated_at"] is None


async def test_save_then_load_round_trip(metrics_env: MetricsEnv) -> None:
    saved = _layout(3)
    put = await metrics_env.client.put(PAGE, json={"layout": saved}, headers=_auth("admin"))
    assert put.status_code == 200
    assert put.json()["layout"] == saved
    assert put.json()["updated_at"] is not None

    got = await metrics_env.client.get(PAGE, headers=_auth("admin"))
    assert got.status_code == 200
    assert got.json()["layout"] == saved


async def test_save_is_idempotent_upsert(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.put(PAGE, json={"layout": _layout(1)}, headers=_auth("admin"))
    await metrics_env.client.put(PAGE, json={"layout": _layout(2)}, headers=_auth("admin"))
    got = await metrics_env.client.get(PAGE, headers=_auth("admin"))
    assert got.json()["layout"] == _layout(2)  # last write wins, single row


async def test_reset_clears_to_default(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.put(PAGE, json={"layout": _layout(5)}, headers=_auth("admin"))
    reset = await metrics_env.client.post(f"{PAGE}/reset", headers=_auth("admin"))
    assert reset.status_code == 200
    assert reset.json()["layout"] is None
    # Subsequent load falls back to default (None).
    assert (await metrics_env.client.get(PAGE, headers=_auth("admin"))).json()["layout"] is None


async def test_layouts_are_private_per_user(metrics_env: MetricsEnv) -> None:
    """admin and finance are different users — neither sees nor overwrites the other."""
    admin_layout = _layout(10)
    finance_layout = _layout(20)
    await metrics_env.client.put(PAGE, json={"layout": admin_layout}, headers=_auth("admin"))

    # finance has saved nothing yet → default fallback, NOT admin's layout.
    finance_before = await metrics_env.client.get(PAGE, headers=_auth("finance"))
    assert finance_before.json()["layout"] is None

    # finance saves their own — must not touch admin's.
    await metrics_env.client.put(PAGE, json={"layout": finance_layout}, headers=_auth("finance"))
    admin_view = (await metrics_env.client.get(PAGE, headers=_auth("admin"))).json()
    finance_view = (await metrics_env.client.get(PAGE, headers=_auth("finance"))).json()
    assert admin_view["layout"] == admin_layout
    assert finance_view["layout"] == finance_layout

    # finance reset must not clear admin's layout.
    await metrics_env.client.post(f"{PAGE}/reset", headers=_auth("finance"))
    after = (await metrics_env.client.get(PAGE, headers=_auth("admin"))).json()
    assert after["layout"] == admin_layout


async def test_save_and_reset_are_audited(metrics_env: MetricsEnv) -> None:
    await metrics_env.client.put(PAGE, json={"layout": _layout(7)}, headers=_auth("admin"))
    await metrics_env.client.post(f"{PAGE}/reset", headers=_auth("admin"))
    async with metrics_env.sessionmaker() as session:
        actions = set(
            (
                await session.execute(
                    select(AuditLog.action).where(
                        AuditLog.action.in_(["dashboard_layout_save", "dashboard_layout_reset"])
                    )
                )
            )
            .scalars()
            .all()
        )
    assert actions == {"dashboard_layout_save", "dashboard_layout_reset"}

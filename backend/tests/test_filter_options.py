"""Cascading filter-options endpoint (/meta/filter-options).

The dropdowns must narrow each other: selecting platform=ios must drop HOUs that only
have Android data — the exact bug the owner reported. Options are also RBAC-scoped and
respect the date window.
"""

from datetime import date
from typing import Any

from app.core.fact_table import FACT_TABLE
from sqlalchemy import insert

from tests.conftest import MetricsEnv

_RANGE = {"date_from": "2026-06-01", "date_to": "2026-06-30"}


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def _seed_platforms(env: MetricsEnv) -> None:
    rows: list[dict[str, Any]] = [
        {"date": date(2026, 6, 1), "canonical_key": "ios-a", "platform": "ios",
         "hou": "HOU_IOS", "rpt_console": "Apple Console", "app_name": "iOS A"},
        {"date": date(2026, 6, 1), "canonical_key": "and-a", "platform": "android",
         "hou": "HOU_AND", "rpt_console": "Google Play Console", "app_name": "Android A"},
    ]
    async with env.sessionmaker() as s:
        for r in rows:
            await s.execute(insert(FACT_TABLE).values(**r))
        await s.commit()


async def test_options_include_all_platforms_when_unfiltered(metrics_env: MetricsEnv) -> None:
    await _seed_platforms(metrics_env)
    body = (
        await metrics_env.client.get(
            "/api/v1/meta/filter-options", params=_RANGE, headers=_auth("admin")
        )
    ).json()
    assert set(body["platforms"]) == {"ios", "android"}
    assert "HOU_IOS" in body["hous"] and "HOU_AND" in body["hous"]
    assert "Apple Console" in body["consoles"] and "Google Play Console" in body["consoles"]


async def test_platform_filter_cascades_to_hou(metrics_env: MetricsEnv) -> None:
    """Selecting platform=ios must remove the Android-only HOU from the options."""
    await _seed_platforms(metrics_env)
    body = (
        await metrics_env.client.get(
            "/api/v1/meta/filter-options",
            params={**_RANGE, "platform": "ios"},
            headers=_auth("admin"),
        )
    ).json()
    assert "HOU_IOS" in body["hous"]
    assert "HOU_AND" not in body["hous"]  # cascaded away
    # A dimension never filters ITSELF out — platform options still list both.
    assert set(body["platforms"]) == {"ios", "android"}
    assert "Google Play Console" not in body["consoles"]


async def test_options_are_rbac_scoped(metrics_env: MetricsEnv) -> None:
    """A pod-scoped user only sees options from their own pod's data, not everyone's."""
    await _seed_platforms(metrics_env)  # these rows have no pod -> outside POD_A
    body = (
        await metrics_env.client.get(
            "/api/v1/meta/filter-options", params=_RANGE, headers=_auth("pod_owner_scoped")
        )
    ).json()
    # POD_A rows (base seed) use hou HOU_A; the unscoped platform rows must NOT appear.
    assert "HOU_A" in body["hous"]
    assert "HOU_IOS" not in body["hous"] and "HOU_AND" not in body["hous"]

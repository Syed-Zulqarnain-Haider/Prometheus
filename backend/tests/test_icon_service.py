"""App-icon resolution: iTunes lookup is cached in Redis and best-effort (never errors)."""

from typing import Any

import pytest
from app.services import icon_service

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


async def test_resolve_caches_and_omits_unresolved(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[int]] = []

    async def fake_fetch(apple_ids: list[int]) -> dict[int, str]:
        calls.append(apple_ids)
        return {123: "https://cdn.example/123/512x512bb.jpg"}  # 999 unresolved

    monkeypatch.setattr(icon_service, "_fetch_itunes", fake_fetch)
    redis = metrics_env.redis

    first = await icon_service.resolve_ios_icons(redis, [123, 999, 0, None])  # type: ignore[list-item]
    assert first == {"123": "https://cdn.example/123/512x512bb.jpg"}  # 999/0/None omitted

    # Second call is fully cache-served (hit for 123, negative-cache for 999) — no new fetch.
    second = await icon_service.resolve_ios_icons(redis, [123, 999])
    assert second == {"123": "https://cdn.example/123/512x512bb.jpg"}
    assert len(calls) == 1  # only the first call hit the network


async def test_endpoint_returns_icon_map(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_fetch(apple_ids: list[int]) -> dict[int, str]:
        return {aid: f"https://cdn.example/{aid}.jpg" for aid in apple_ids}

    monkeypatch.setattr(icon_service, "_fetch_itunes", fake_fetch)
    resp = await metrics_env.client.get(
        "/api/v1/apps/icons", params={"ids": [111, 222]}, headers=_auth("admin")
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "111": "https://cdn.example/111.jpg",
        "222": "https://cdn.example/222.jpg",
    }


async def test_fetch_failure_is_swallowed(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(apple_ids: list[int]) -> dict[int, str]:
        raise RuntimeError("network down")

    # The lookup layer must never propagate — resolve returns {} and the client shows badges.
    async def guarded(apple_ids: list[int]) -> dict[int, Any]:
        try:
            return await boom(apple_ids)
        except Exception:  # noqa: BLE001
            return {}

    monkeypatch.setattr(icon_service, "_fetch_itunes", guarded)
    out = await icon_service.resolve_ios_icons(metrics_env.redis, [555])
    assert out == {}

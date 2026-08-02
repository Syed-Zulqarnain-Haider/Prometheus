"""Ask-your-data assistant.

The model is mocked (a scripted fake Anthropic client), but every tool call runs through the
REAL scoped QueryBuilder against the REAL seeded fact table — so these tests exercise the
actual RBAC path the assistant uses, not a stub of it.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.schemas.auth import ScopeOut, UserContext
from app.services import chat_service
from app.services.query_builder import QueryBuilder

from tests.conftest import MetricsEnv


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


# ── A tiny scripted stand-in for the Anthropic async client ──────────────────
class _Block:
    def __init__(
        self,
        type: str,
        *,
        text: str | None = None,
        id: str | None = None,
        name: str | None = None,
        input: dict[str, Any] | None = None,
    ) -> None:
        self.type = type
        self.text = text
        self.id = id
        self.name = name
        self.input = input


class _Msg:
    def __init__(self, content: list[_Block], stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, script: list[_Msg]) -> None:
        self._script = script
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _Msg:
        self.calls.append(kwargs)
        return self._script.pop(0)


class _FakeClient:
    def __init__(self, script: list[_Msg]) -> None:
        self.messages = _FakeMessages(script)


def _install_fake(monkeypatch: pytest.MonkeyPatch, script: list[_Msg]) -> _FakeClient:
    client = _FakeClient(script)
    monkeypatch.setattr(chat_service, "is_configured", lambda settings: True)
    monkeypatch.setattr(chat_service, "_create_client", lambda settings: client)
    return client


async def _enable_chat(env: MetricsEnv) -> None:
    resp = await env.client.put(
        "/api/v1/admin/settings/chat_enabled", json={"value": True}, headers=_auth("admin")
    )
    assert resp.status_code == 200


# ── status + gating ──────────────────────────────────────────────────────────
async def test_status_unavailable_by_default(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get("/api/v1/chat/status", headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["enabled"] is False  # chat_enabled defaults off


async def test_status_available_when_enabled_and_configured(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake(monkeypatch, [])
    await _enable_chat(metrics_env)
    resp = await metrics_env.client.get("/api/v1/chat/status", headers=_auth("viewer"))
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"available": True, "configured": True, "enabled": True, "reason": None}


async def test_chat_requires_auth(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code == 401


async def test_chat_disabled_returns_503(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Configured but the admin setting is still off → clean 503, no model call.
    _install_fake(monkeypatch, [])
    resp = await metrics_env.client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "revenue?"}]},
        headers=_auth("admin"),
    )
    assert resp.status_code == 503


async def test_chat_not_configured_returns_503(metrics_env: MetricsEnv) -> None:
    # Enabled but no API key configured (default) → clean 503.
    await _enable_chat(metrics_env)
    resp = await metrics_env.client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "revenue?"}]},
        headers=_auth("admin"),
    )
    assert resp.status_code == 503


async def test_chat_rejects_non_user_last_message(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake(monkeypatch, [])
    await _enable_chat(metrics_env)
    resp = await metrics_env.client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "assistant", "content": "hi"}]},
        headers=_auth("admin"),
    )
    assert resp.status_code == 422


# ── end-to-end tool loop (real RBAC-scoped queries) ──────────────────────────
async def test_chat_answers_using_scoped_totals(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = [
        _Msg(
            [
                _Block(
                    "tool_use",
                    id="t1",
                    name="get_totals",
                    input={"date_from": "2026-06-01", "date_to": "2026-06-30"},
                )
            ],
            stop_reason="tool_use",
        ),
        _Msg([_Block("text", text="Total revenue was $1,080.")], stop_reason="end_turn"),
    ]
    client = _install_fake(monkeypatch, script)
    await _enable_chat(metrics_env)

    resp = await metrics_env.client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "What was revenue in June?"}]},
        headers=_auth("admin"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Total revenue was $1,080."
    assert body["tool_calls"] == 1

    # The tool result fed back to the model carried the REAL scoped totals (admin sees all
    # 4 seeded rows: 600+400+70+10 = 1080), proving the tool queried the DB through RBAC.
    second_call_messages = client.messages.calls[1]["messages"]
    tool_result = second_call_messages[-1]["content"][0]
    assert tool_result["is_error"] is False
    assert "1080" in tool_result["content"]


async def test_chat_tool_error_on_forbidden_metric_via_loop(
    metrics_env: MetricsEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A viewer (store_installs only) — the model asks to rank by total_revenue_usd, which is
    # not permitted. The loop must feed back a recoverable tool error, never leak the number.
    script = [
        _Msg(
            [
                _Block(
                    "tool_use",
                    id="t1",
                    name="get_breakdown",
                    input={
                        "date_from": "2026-06-01",
                        "date_to": "2026-06-30",
                        "group_by": "app",
                        "metric": "total_revenue_usd",
                    },
                )
            ],
            stop_reason="tool_use",
        ),
        _Msg(
            [_Block("text", text="You don't have access to revenue.")],
            stop_reason="end_turn",
        ),
    ]
    client = _install_fake(monkeypatch, script)
    await _enable_chat(metrics_env)

    resp = await metrics_env.client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "top apps by revenue?"}]},
        headers=_auth("viewer"),
    )
    assert resp.status_code == 200
    tool_result = client.messages.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "not permitted" in tool_result["content"]
    # And no revenue figure was ever handed to the model.
    assert "1080" not in tool_result["content"]


# ── the RBAC guarantee at the tool layer, model-free ─────────────────────────
def _ctx(role: str, groups: list[str], scopes: list[ScopeOut]) -> UserContext:
    return UserContext(
        user_id=uuid.uuid4(),
        firebase_uid=f"{role}-x",
        email=f"{role}@terafort.org",
        is_active=True,
        roles=[role],
        metric_groups=groups,
        capabilities=[],
        scopes=scopes,
    )


async def test_run_tool_enforces_metric_permission(metrics_env: MetricsEnv) -> None:
    qb = QueryBuilder(_ctx("viewer", ["store_installs"], [ScopeOut(scope_type="all")]))
    base = {"date_from": "2026-06-01", "date_to": "2026-06-30", "group_by": "app"}
    async with metrics_env.sessionmaker() as s:
        forbidden = await chat_service._run_tool(
            s, qb, "get_breakdown", {**base, "metric": "total_revenue_usd"}
        )
        assert "error" in forbidden and "not permitted" in forbidden["error"]

        allowed = await chat_service._run_tool(
            s, qb, "get_breakdown", {**base, "metric": "store_total_installs"}
        )
        assert "error" not in allowed
        assert allowed["rows"]


async def test_run_tool_enforces_row_scope(metrics_env: MetricsEnv) -> None:
    # A pod-scoped user (POD_A) must only ever see POD_A rows, even via the assistant.
    qb = QueryBuilder(
        _ctx(
            "pod_owner",
            ["store_installs", "ua_spend", "ad_revenue", "iap_revenue", "profitability"],
            [ScopeOut(scope_type="pod", scope_value="POD_A")],
        )
    )
    async with metrics_env.sessionmaker() as s:
        out = await chat_service._run_tool(
            s,
            qb,
            "get_breakdown",
            {
                "date_from": "2026-06-01",
                "date_to": "2026-06-30",
                "group_by": "pod",
                "metric": "total_revenue_usd",
            },
        )
        pods = {row["pod"] for row in out["rows"]}
        assert pods == {"POD_A"}  # POD_B is invisible to this scope


async def test_run_tool_bad_dates_are_recoverable(metrics_env: MetricsEnv) -> None:
    qb = QueryBuilder(_ctx("admin", ["profitability"], [ScopeOut(scope_type="all")]))
    async with metrics_env.sessionmaker() as s:
        out = await chat_service._run_tool(
            s, qb, "get_totals", {"date_from": "not-a-date", "date_to": "2026-06-30"}
        )
        assert "error" in out

"""The ask-your-data assistant — a natural-language question answerer over the metrics.

RBAC is not bolted on; it is the ONLY way this service touches data. Claude runs a manual
tool-use loop, but every tool executes through the CALLER's scoped ``QueryBuilder(context)``,
which:

  * injects the caller's row-scope WHERE clause FIRST (client filters can only narrow), and
  * only ever aggregates the caller's permitted metric groups.

So the assistant can never read a row or a column the user could not read themselves. There is
NO text-to-SQL and no raw-SQL path: the model can only choose a date range, a few narrowing
filters, a group-by dimension, and a metric NAME — all validated against the same registry the
REST API uses. An unknown/forbidden metric or a malformed date comes back to the model as a
tool error, which it can recover from; it never reaches the database as SQL.

The Anthropic client is created lazily (so ``anthropic`` need not be importable when the
feature is unconfigured), and can be injected for testing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.chat import ChatMessage
from app.schemas.metrics import GroupBy, MetricFilters
from app.services import metrics_service
from app.services.query_builder import QueryBuilder

log = logging.getLogger("app.services.chat")

# group_by / filter dimensions the assistant may use (subset of the full filter surface —
# these cover the questions people actually ask and keep the tool schema small).
_GROUP_BY = ["app", "pod", "publisher", "platform", "hou"]
_MAX_BREAKDOWN_LIMIT = 50

_FILTER_PROPS: dict[str, Any] = {
    "date_from": {"type": "string", "description": "Start date, inclusive (YYYY-MM-DD)."},
    "date_to": {"type": "string", "description": "End date, inclusive (YYYY-MM-DD)."},
    "platform": {"type": "string", "enum": ["ios", "android"], "description": "Optional."},
    "apps": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional canonical_key values to narrow to specific apps.",
    },
    "pods": {"type": "array", "items": {"type": "string"}, "description": "Optional pod numbers."},
    "publishers": {"type": "array", "items": {"type": "string"}, "description": "Optional."},
    "hou": {"type": "array", "items": {"type": "string"}, "description": "Optional HOU values."},
}


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_totals",
            "description": (
                "Aggregate totals across a date range for the metrics the user is permitted "
                "to see. Returns summed measures plus derived KPIs (roas, ad_roas, cpi, "
                "*_ecpm, *_ctr, profit_margin, net_revenue_usd, gross_profit_usd) computed "
                "from those totals. Set compare=true to also get the immediately-preceding "
                "equal-length period under 'previous'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    **_FILTER_PROPS,
                    "compare": {
                        "type": "boolean",
                        "description": "Also return the previous equal-length period.",
                    },
                },
                "required": ["date_from", "date_to"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_breakdown",
            "description": (
                "Rank a single metric by a dimension over a date range (e.g. top apps by "
                "total_revenue_usd). Returns rows sorted by the metric descending."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    **_FILTER_PROPS,
                    "group_by": {"type": "string", "enum": _GROUP_BY},
                    "metric": {
                        "type": "string",
                        "description": "One permitted metric name to rank by.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"How many rows (1-{_MAX_BREAKDOWN_LIMIT}).",
                    },
                },
                "required": ["date_from", "date_to", "group_by", "metric"],
                "additionalProperties": False,
            },
        },
    ]


def _system_prompt(qb: QueryBuilder, today: date) -> str:
    measures = ", ".join(sorted(qb.permitted_measures)) or "(none)"
    return (
        "You are the assistant for Prometheus, an internal mobile-app performance analytics "
        "dashboard. You answer questions about the data using ONLY the provided tools — never "
        "invent numbers, and never claim a figure you did not get from a tool.\n\n"
        f"Today is {today.isoformat()}. All money is in USD. When the user gives a relative "
        "range ('last month', 'yesterday', 'this quarter'), convert it to explicit dates "
        "yourself before calling a tool.\n\n"
        "The tools already enforce this user's access: they only ever return data this user is "
        "permitted to see. If a tool reports a metric is not permitted, tell the user they do "
        "not have access to that metric — do NOT try to work around it.\n\n"
        f"Metrics this user may query: {measures}.\n"
        "Derived KPIs available from get_totals: roas, ad_roas, cpi, admob_ecpm, "
        "applovin_ecpm, *_ctr, organic_install_share, profit_margin, net_revenue_usd, "
        "gross_profit_usd (each only when its component metrics are permitted).\n"
        "Breakdown dimensions: app, pod, publisher, platform, hou.\n\n"
        "Be concise and factual. Prefer a short sentence with the key number, then a compact "
        "table or bullet list for breakdowns. Note that Apple data can lag ~2-3 days, so the "
        "most recent day may be incomplete. If a question is not about this data, say so "
        "briefly rather than guessing."
    )


@dataclass
class ChatAnswer:
    text: str
    tool_calls: int


def is_configured(settings: Settings) -> bool:
    """The assistant is configured iff an Anthropic API key is present (env/Secret Manager)."""
    return bool(settings.anthropic_api_key)


def _create_client(settings: Settings) -> Any:
    """Build an async Anthropic client. Imported lazily so the package is only required when
    the feature is actually configured and used."""
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _parse_filters(args: dict[str, Any]) -> MetricFilters:
    """Build a validated MetricFilters from tool input. Raises ValueError on bad dates /
    out-of-bounds ranges (surfaced back to the model as a recoverable tool error)."""
    try:
        date_from = date.fromisoformat(str(args["date_from"]))
        date_to = date.fromisoformat(str(args["date_to"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("date_from and date_to must be YYYY-MM-DD dates") from exc
    return MetricFilters(
        date_from=date_from,
        date_to=date_to,
        compare=bool(args.get("compare", False)),
        platform=args.get("platform"),
        apps=list(args.get("apps") or []),
        pods=list(args.get("pods") or []),
        publishers=list(args.get("publishers") or []),
        hou=list(args.get("hou") or []),
    )


async def _run_tool(
    db: AsyncSession, qb: QueryBuilder, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    """Execute one assistant tool call through the scoped query builder. Any error is
    returned as ``{"error": ...}`` so the model can adjust rather than the request failing."""
    try:
        filters = _parse_filters(args)
        if name == "get_totals":
            return await metrics_service.run_summary(db, qb, filters)
        if name == "get_breakdown":
            metric = str(args.get("metric", ""))
            group_by = str(args.get("group_by", ""))
            if group_by not in _GROUP_BY:
                raise ValueError(f"group_by must be one of {_GROUP_BY}")
            limit = int(args.get("limit") or 10)
            limit = max(1, min(_MAX_BREAKDOWN_LIMIT, limit))
            # run_breakdown validates the metric against permitted measures for us.
            return await metrics_service.run_breakdown(
                db, qb, filters, cast(GroupBy, group_by), [metric], limit
            )
        return {"error": f"unknown tool: {name}"}
    except ValueError as exc:
        return {"error": str(exc)}


def _text_of(content: Any) -> str:
    return "".join(getattr(b, "text", "") for b in content if getattr(b, "type", "") == "text")


async def answer_question(
    db: AsyncSession,
    context: Any,
    settings: Settings,
    messages: list[ChatMessage],
    *,
    client: Any = None,
) -> ChatAnswer:
    """Run the tool-use loop and return the assistant's final answer.

    Every data lookup goes through ``QueryBuilder(context)`` so the answer can only ever
    reflect data the caller is permitted to see.
    """
    if client is None:
        client = _create_client(settings)

    qb = QueryBuilder(context)
    tools = _tool_specs()
    system = _system_prompt(qb, date.today())
    convo: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in messages]

    tool_calls = 0
    response: Any = None
    for _ in range(max(1, settings.chat_max_iterations)):
        response = await client.messages.create(
            model=settings.chat_model,
            max_tokens=settings.chat_max_tokens,
            system=system,
            tools=tools,
            messages=convo,
        )
        if getattr(response, "stop_reason", None) != "tool_use":
            break

        convo.append({"role": "assistant", "content": response.content})
        results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            tool_calls += 1
            out = await _run_tool(db, qb, block.name, dict(block.input or {}))
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, default=str),
                    "is_error": "error" in out,
                }
            )
        convo.append({"role": "user", "content": results})
    else:
        # Loop exhausted without a natural end — ask for a final answer with no tools so we
        # never return an empty message.
        log.info("chat loop hit iteration cap; requesting a final answer")
        response = await client.messages.create(
            model=settings.chat_model,
            max_tokens=settings.chat_max_tokens,
            system=system,
            messages=convo,
        )

    text = _text_of(response.content) if response is not None else ""
    if not text.strip():
        text = "I couldn't produce an answer for that. Try rephrasing your question."
    return ChatAnswer(text=text.strip(), tool_calls=tool_calls)

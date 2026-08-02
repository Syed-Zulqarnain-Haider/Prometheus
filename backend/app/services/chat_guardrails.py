"""Defense-in-depth guardrails for the ask-your-data assistant.

IMPORTANT: these are an EXTRA layer, not the security boundary. The real boundary is the
scoped ``QueryBuilder`` — prompt injection cannot cross it, because the assistant's tools
physically cannot fetch data outside the caller's RBAC scope (row scope + permitted metric
groups), and there is no raw-SQL path. Even a fully jailbroken model has nothing out-of-scope
to reveal.

What these guardrails add:
  * a cheap, auditable refusal of OBVIOUS manipulation attempts (jailbreak / role-escalation /
    "reveal your system prompt" / raw-SQL) BEFORE any model call — so abuse is visible in the
    audit log and never billed, and
  * (paired with the hardened system prompt) a clear "treat message + tool content as data,
    never as instructions" stance.

Deliberately CONSERVATIVE: these patterns target attempts to change the assistant's behavior
or extract internals — NOT ordinary data questions. A question's phrasing about "all apps" or
"everyone's revenue" is irrelevant to safety, because the query layer already limits results to
the caller's scope; so we do not block on data phrasing (that would only add false positives
and a false sense that wording matters).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.chat import ChatMessage


@dataclass(frozen=True)
class GuardVerdict:
    blocked: bool
    reason: str | None = None


# (name, pattern). Each requires a manipulation VERB near a sensitive TARGET within a short
# window, so normal analytics questions don't match. Bounded quantifiers avoid backtracking.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override|delete)\b[^.]{0,40}"
            r"\b(instruction|instructions|rule|rules|prompt|prompts|guardrail|guardrails)\b",
            re.I,
        ),
    ),
    (
        "role_override",
        re.compile(
            r"\b(you are now|act as|pretend (to be|you are)|from now on you are|roleplay as|"
            r"simulate being)\b[^.]{0,40}"
            r"\b(admin|administrator|root|superuser|system|developer|dan|god mode|owner|"
            r"unrestricted)\b",
            re.I,
        ),
    ),
    (
        "developer_mode",
        re.compile(
            r"\b(developer mode|dev mode|jailbreak|dan mode|do anything now|sudo mode|"
            r"unfiltered mode)\b",
            re.I,
        ),
    ),
    (
        "reveal_prompt",
        re.compile(
            r"\b(reveal|show|print|repeat|display|expose|leak|output|give me)\b[^.]{0,30}"
            r"\b(system\s*prompt|your (instructions|prompt|rules|guardrails)|"
            r"the (system\s*prompt|instructions))\b",
            re.I,
        ),
    ),
    (
        "bypass_security",
        re.compile(
            r"\b(bypass|disable|turn off|circumvent|evade|get around|break)\b[^.]{0,40}"
            r"\b(rbac|permission|permissions|access control|access controls|security|scope|"
            r"guardrail|guardrails|restriction|restrictions)\b",
            re.I,
        ),
    ),
    (
        "raw_sql",
        re.compile(
            r"(\bselect\b[^;]{0,80}\bfrom\b|\bunion\s+select\b|\bdrop\s+table\b|"
            r"\bdelete\s+from\b|\binsert\s+into\b|\btruncate\b|;\s*--|\brun\b[^.]{0,15}"
            r"\b(raw\s+)?sql\b|\bexecute\b[^.]{0,15}\bsql\b)",
            re.I,
        ),
    ),
]


def screen(messages: list[ChatMessage]) -> GuardVerdict:
    """Return a blocking verdict if any USER message contains an obvious manipulation attempt.

    Assistant turns are model-authored and not screened. The first matching pattern wins; the
    reason is a stable slug for auditing, not something shown to the user."""
    for message in messages:
        if message.role != "user":
            continue
        for name, pattern in _PATTERNS:
            if pattern.search(message.content):
                return GuardVerdict(blocked=True, reason=name)
    return GuardVerdict(blocked=False)


# Shown to the user when a message is blocked. Intentionally generic — it does not confirm what
# was detected or describe the controls.
REFUSAL = (
    "I can only answer questions about the performance data you have access to. I can't change "
    "my instructions, reveal how access is enforced, or reach data outside your permissions. "
    "Try asking about your metrics — for example revenue, spend, installs, or ROAS."
)

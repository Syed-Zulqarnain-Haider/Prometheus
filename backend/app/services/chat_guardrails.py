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
        # Concrete SQL SHAPES only — NOT the bare word "select … from", which matches ordinary
        # English ("select the top 5 apps from June"). Real analytics questions never match.
        "raw_sql",
        re.compile(
            r"(\bunion\s+select\b|\bdrop\s+table\b|\bdelete\s+from\b|\binsert\s+into\b|"
            r"\btruncate\s+table\b|\bselect\s+\*\s+from\b|\bfrom\s+\w+\.\w+|;\s*--|"
            r"\brun\b[^.]{0,15}\bsql\b|\bexecute\b[^.]{0,15}\bsql\b)",
            re.I,
        ),
    ),
]


def screen(messages: list[ChatMessage]) -> GuardVerdict:
    """Return a blocking verdict if the CURRENT user message is an obvious manipulation attempt.

    Only the latest user turn is screened — each message is screened once, at submission time
    (when it is the latest). Screening the whole history instead would let a single earlier
    false-positive permanently 'poison' a conversation (every later question refused). Assistant
    turns are model-authored and never screened. The RBAC boundary — not this heuristic — is
    what actually protects data, so this can be lenient without loss of safety."""
    latest = next((m for m in reversed(messages) if m.role == "user"), None)
    if latest is None:
        return GuardVerdict(blocked=False)
    for name, pattern in _PATTERNS:
        if pattern.search(latest.content):
            return GuardVerdict(blocked=True, reason=name)
    return GuardVerdict(blocked=False)


# Shown to the user when a message is blocked. Intentionally generic — it does not confirm what
# was detected or describe the controls.
REFUSAL = (
    "I can only answer questions about the performance data you have access to. I can't change "
    "my instructions, reveal how access is enforced, or reach data outside your permissions. "
    "Try asking about your metrics — for example revenue, spend, installs, or ROAS."
)

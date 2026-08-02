"""Request/response schemas for the ask-your-data assistant."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Bounds guard the endpoint against oversized / runaway conversations (each turn is
# echoed back to the model, so the whole transcript is billed on every request).
MAX_MESSAGES = 20
MAX_CONTENT_LEN = 4000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LEN)


class ChatRequest(BaseModel):
    """A chat transcript. The final message must be the user's current question; any
    earlier messages are prior turns kept for context."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    # Which LLM should answer (e.g. "claude", "openai", "gemini", "grok"). None → the first
    # configured provider. Validated server-side against the available providers.
    provider: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _last_is_user(self) -> ChatRequest:
        if self.messages[-1].role != "user":
            raise ValueError("the last message must be from the user")
        return self


class ChatResponse(BaseModel):
    answer: str
    # How many scoped data lookups the assistant ran to produce the answer (transparency).
    tool_calls: int = 0
    # Which provider actually answered (echoed back so the UI can confirm the selection).
    provider: str


class ProviderInfo(BaseModel):
    """A selectable LLM provider (only ever the configured ones; keys are never exposed)."""

    id: str
    label: str


class ChatStatus(BaseModel):
    """Whether the assistant is usable for this caller, and why not if it isn't."""

    available: bool
    # True when at least one provider API key is set in the environment (secret, never here).
    configured: bool
    # True when the admin ``chat_enabled`` operational setting is on.
    enabled: bool
    # The configured providers the user may pick from (empty when none are configured).
    providers: list[ProviderInfo] = []
    reason: str | None = None

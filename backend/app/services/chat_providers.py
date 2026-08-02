"""LLM provider registry for the ask-your-data assistant.

The user picks WHICH model answers (Claude, ChatGPT, Gemini, Grok, …); this module is the
single source of truth for the choices. Two things never change with the provider:

  * the RBAC tool-execution layer (every tool runs through the caller's scoped
    ``QueryBuilder`` — see ``chat_service``), and
  * secret handling — every provider key is read from the environment (Secret Manager in
    prod), NEVER stored in the DB or exposed by any endpoint.

A provider is "available" iff its API key is configured. Model ids for the non-Anthropic
providers are env-overridable because third-party model names change independently of this
app. Grok (xAI) and Gemini are reached through their OpenAI-compatible endpoints, so a
single OpenAI-style adapter drives all three (see ``chat_service._run_openai_loop``).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings

# Provider "kind" selects the client + loop implementation in chat_service.
ANTHROPIC = "anthropic"
OPENAI_COMPAT = "openai_compat"


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    kind: str
    # Settings attribute names (never the values) for the secret key + the model id.
    key_attr: str
    model_attr: str
    # OpenAI-compatible base URL (None → the OpenAI default). Ignored for the Anthropic kind.
    base_url: str | None = None


# Order here is the order shown in the UI dropdown.
PROVIDERS: dict[str, Provider] = {
    "claude": Provider("claude", "Claude", ANTHROPIC, "anthropic_api_key", "chat_model"),
    "openai": Provider("openai", "ChatGPT", OPENAI_COMPAT, "openai_api_key", "openai_model"),
    "gemini": Provider(
        "gemini",
        "Gemini",
        OPENAI_COMPAT,
        "gemini_api_key",
        "gemini_model",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "grok": Provider(
        "grok",
        "Grok",
        OPENAI_COMPAT,
        "xai_api_key",
        "grok_model",
        base_url="https://api.x.ai/v1",
    ),
}


def api_key(settings: Settings, provider: Provider) -> str | None:
    value = getattr(settings, provider.key_attr, None)
    return str(value) if value else None


def model_id(settings: Settings, provider: Provider) -> str:
    return str(getattr(settings, provider.model_attr))


def is_available(settings: Settings, provider: Provider) -> bool:
    return bool(api_key(settings, provider))


def available_providers(settings: Settings) -> list[Provider]:
    """Providers with a configured key, in registry order. Never exposes the keys."""
    return [p for p in PROVIDERS.values() if is_available(settings, p)]


def resolve(settings: Settings, provider_id: str | None) -> Provider:
    """Pick the requested provider (or the first available one). Raises ValueError if the
    id is unknown or that provider is not configured — surfaced as a clean 4xx, never a 500."""
    available = available_providers(settings)
    if not available:
        raise ValueError("no chat provider is configured")
    if provider_id is None:
        return available[0]
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise ValueError(f"unknown provider: {provider_id}")
    if not is_available(settings, provider):
        raise ValueError(f"provider not configured: {provider_id}")
    return provider


def any_configured(settings: Settings) -> bool:
    return bool(available_providers(settings))

"""Pure helpers for Claude runtime setup and request assembly."""

from __future__ import annotations

from typing import Any


def build_claude_transport_impl(
    settings,
    *,
    anthropic_module,
    httpx_module,
):
    """Create the Anthropic transport from settings and injected modules."""
    client = anthropic_module.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        max_retries=settings.claude_max_retries,
        http_client=httpx_module.AsyncClient(
            limits=httpx_module.Limits(
                max_connections=settings.claude_max_connections,
                max_keepalive_connections=settings.claude_keepalive_connections,
                keepalive_expiry=settings.claude_keepalive_expiry,
            ),
        ),
    )
    return client, settings.claude_models


def build_thinking_config(effort: str | None, budget_tokens: int) -> dict | None:
    """Build the Claude thinking config, or return None when disabled."""
    if effort is not None:
        return {"type": "adaptive"}
    return {"type": "enabled", "budget_tokens": budget_tokens}


def build_adaptive_thinking_config(effort: str | None) -> dict | None:
    """Build the adaptive thinking config used by text completions."""
    if effort is None:
        return None
    return {"type": "adaptive"}


# Adaptive thinking is not available on Haiku-family models.
_THINKING_UNSUPPORTED_SUBSTRINGS = ("haiku",)


def model_supports_adaptive_thinking(model: str) -> bool:
    """Return True if the model supports adaptive thinking."""
    model_lower = model.lower()
    return not any(s in model_lower for s in _THINKING_UNSUPPORTED_SUBSTRINGS)


def build_stream_kwargs(
    *,
    model: str,
    max_tokens: int,
    system: str | list,
    messages: list[dict],
    response_model: type | None = None,
    thinking: dict | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Assemble Claude streaming kwargs with the right mutually exclusive knobs."""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if response_model is not None:
        kwargs["output_format"] = response_model
    if thinking is not None:
        kwargs["thinking"] = thinking
    elif temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs

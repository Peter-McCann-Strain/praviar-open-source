from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.clients.claude_runtime_helpers import (
    build_adaptive_thinking_config,
    build_claude_transport_impl,
    build_stream_kwargs,
    build_thinking_config,
    model_supports_adaptive_thinking,
)


def test_model_supports_adaptive_thinking_haiku_excluded() -> None:
    assert not model_supports_adaptive_thinking("claude-haiku-4-5-20251001")
    assert not model_supports_adaptive_thinking("claude-haiku-3-5-20241022")
    assert model_supports_adaptive_thinking("claude-sonnet-4-6")
    assert model_supports_adaptive_thinking("claude-opus-4-8")
    assert model_supports_adaptive_thinking("claude-3-7-sonnet-20250219")


def test_build_claude_transport_impl_uses_injected_modules() -> None:
    class FakeHttpx:
        class Limits:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class AsyncClient:
            def __init__(self, *, limits):
                self.limits = limits

    class FakeAnthropic:
        class AsyncAnthropic:
            def __init__(self, *, api_key, max_retries, http_client):
                self.api_key = api_key
                self.max_retries = max_retries
                self.http_client = http_client

    settings = SimpleNamespace(
        anthropic_api_key="key",
        claude_max_retries=4,
        claude_max_connections=8,
        claude_keepalive_connections=3,
        claude_keepalive_expiry=9,
        claude_models=SimpleNamespace(analysis="analysis", deep="deep", triage="triage"),
    )

    client, models = build_claude_transport_impl(
        settings,
        anthropic_module=FakeAnthropic,
        httpx_module=FakeHttpx,
    )

    assert client.api_key == "key"
    assert client.max_retries == 4
    assert client.http_client.limits.kwargs == {
        "max_connections": 8,
        "max_keepalive_connections": 3,
        "keepalive_expiry": 9,
    }
    assert models is settings.claude_models


def test_build_thinking_config_prefers_effort_over_budget() -> None:
    assert build_thinking_config("low", 32000) == {"type": "adaptive"}
    assert build_thinking_config(None, 64000) == {"type": "enabled", "budget_tokens": 64000}
    assert build_adaptive_thinking_config("medium") == {"type": "adaptive"}
    assert build_adaptive_thinking_config(None) is None


def test_build_stream_kwargs_handles_output_format_and_thinking() -> None:
    kwargs = build_stream_kwargs(
        model="model",
        max_tokens=128,
        system="system",
        messages=[{"role": "user", "content": "hi"}],
        response_model=SimpleNamespace,
        thinking={"type": "enabled", "budget_tokens": 1},
        temperature=0.3,
    )

    assert kwargs["model"] == "model"
    assert kwargs["output_format"] is SimpleNamespace
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 1}
    assert "temperature" not in kwargs

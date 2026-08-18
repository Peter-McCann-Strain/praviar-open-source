from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from praviar_pipeline.clients.claude import ClaudeClient, PaidApiBlockedError
from praviar_pipeline.clients.claude_runtime import complete_text_impl, tool_use_loop_impl
from praviar_pipeline.cost_tracker import CostTracker, set_current_tracker
from praviar_pipeline.errors import PaidCallBudgetExceededError


def test_claude_client_constructs_transport_from_settings(monkeypatch) -> None:
    client = object()
    models = SimpleNamespace(analysis="analysis-model", deep="deep-model", triage="triage-model")
    settings = SimpleNamespace(anthropic_api_key="key", claude_models=models)

    build_transport = MagicMock(return_value=(client, models))
    monkeypatch.setattr("praviar_pipeline.clients.claude.build_claude_transport", build_transport)
    monkeypatch.setattr(
        "praviar_pipeline.clients.claude.get_settings", MagicMock(return_value=settings)
    )
    monkeypatch.setattr("praviar_pipeline.clients.claude.assert_paid_api_allowed", lambda _: None)

    claude = ClaudeClient()

    assert claude._client is client
    assert claude._models is models
    build_transport.assert_called_once_with(settings)


def test_claude_client_blocks_live_transport_in_no_paid_mode(monkeypatch) -> None:
    build_transport = MagicMock()
    monkeypatch.setenv("NO_PAID_API", "true")
    monkeypatch.setattr("praviar_pipeline.clients.claude.build_claude_transport", build_transport)

    with pytest.raises(PaidApiBlockedError, match="NO_PAID_API=true"):
        ClaudeClient()

    build_transport.assert_not_called()


@pytest.mark.asyncio
async def test_claude_client_complete_delegates(monkeypatch) -> None:
    client = object()
    models = SimpleNamespace(analysis="analysis-model", deep="deep-model", triage="triage-model")
    claude = object.__new__(ClaudeClient)
    claude._client = client
    claude._models = models

    complete_impl_mock = AsyncMock(return_value=("parsed", {"input_tokens": 3, "output_tokens": 4}))
    monkeypatch.setattr("praviar_pipeline.clients.claude.complete_impl", complete_impl_mock)

    result = await ClaudeClient.complete(
        claude,
        system="system",
        user="user",
        response_model=SimpleNamespace,
        model="override-model",
        max_tokens=321,
        temperature=0.7,
        effort="low",
        cache_system=False,
    )

    assert result == ("parsed", {"input_tokens": 3, "output_tokens": 4})
    complete_impl_mock.assert_awaited_once_with(
        client=client,
        models=models,
        system="system",
        user="user",
        response_model=SimpleNamespace,
        model="override-model",
        max_tokens=321,
        temperature=0.7,
        effort="low",
        cache_system=False,
        role="unknown",
    )


@pytest.mark.asyncio
async def test_claude_client_complete_text_delegates(monkeypatch) -> None:
    client = object()
    models = SimpleNamespace(analysis="analysis-model", deep="deep-model", triage="triage-model")
    settings = SimpleNamespace(max_tool_rounds=7)
    claude = object.__new__(ClaudeClient)
    claude._client = client
    claude._models = models

    complete_text_impl_mock = AsyncMock(
        return_value=("text", {"input_tokens": 1, "output_tokens": 2})
    )
    monkeypatch.setattr(
        "praviar_pipeline.clients.claude.complete_text_impl", complete_text_impl_mock
    )
    monkeypatch.setattr(
        "praviar_pipeline.clients.claude.get_settings", MagicMock(return_value=settings)
    )

    result = await ClaudeClient.complete_text(
        claude,
        system="system",
        user="user",
        model="override-model",
        max_tokens=123,
        temperature=0.3,
        effort="medium",
        toolkit=None,
        cache_system=True,
    )

    assert result == ("text", {"input_tokens": 1, "output_tokens": 2})
    complete_text_impl_mock.assert_awaited_once_with(
        client=client,
        models=models,
        system="system",
        user="user",
        model="override-model",
        max_tokens=123,
        temperature=0.3,
        effort="medium",
        toolkit=None,
        cache_system=True,
        max_rounds=7,
        tool_use_loop=tool_use_loop_impl,
        role="unknown",
    )


@pytest.mark.asyncio
async def test_complete_text_impl_honors_explicit_model(monkeypatch) -> None:
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="answer")],
        usage=SimpleNamespace(input_tokens=9, output_tokens=4),
        stop_reason="end_turn",
    )

    class FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_final_message(self):
            return response

    messages = SimpleNamespace(stream=MagicMock(return_value=FakeStream()))
    client = SimpleNamespace(messages=messages)
    models = SimpleNamespace(analysis="analysis-model")
    log_llm_call = MagicMock()
    monkeypatch.setattr("praviar_pipeline.clients.claude_runtime.log_llm_call", log_llm_call)

    text, usage = await complete_text_impl(
        client=client,
        models=models,
        system="system",
        user="user",
        model="override-model",
        max_tokens=42,
        temperature=0.0,
        toolkit=None,
        cache_system=False,
    )

    assert text == "answer"
    assert usage["model"] == "override-model"
    messages.stream.assert_called_once()
    assert messages.stream.call_args.kwargs["model"] == "override-model"


@pytest.mark.asyncio
async def test_complete_text_impl_blocks_unknown_pricing_before_provider_call() -> None:
    messages = SimpleNamespace(stream=MagicMock())
    client = SimpleNamespace(messages=messages)
    models = SimpleNamespace(analysis="claude-unpriced-future-model")
    set_current_tracker(CostTracker(hard_budget_usd=15.0))
    try:
        with pytest.raises(PaidCallBudgetExceededError, match="no verified pricing"):
            await complete_text_impl(
                client=client,
                models=models,
                system="system",
                user="user",
                max_tokens=42,
                temperature=0.0,
                toolkit=None,
                cache_system=False,
            )
    finally:
        set_current_tracker(None)

    messages.stream.assert_not_called()

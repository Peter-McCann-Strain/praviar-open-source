from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from praviar_pipeline.clients.claude_runtime_results import log_and_build_usage


def test_log_and_build_usage_logs_and_returns_usage(monkeypatch) -> None:
    response = SimpleNamespace(
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=7, output_tokens=3),
    )
    log_llm_call = MagicMock()
    monkeypatch.setattr(
        "praviar_pipeline.clients.claude_runtime_results.log_llm_call", log_llm_call
    )

    usage, cache_read, cache_creation = log_and_build_usage(
        purpose="complete_text",
        response=response,
        model="claude-model",
        total_input=7,
        total_output=3,
        duration_s=1.25,
        tool_calls=2,
    )

    assert usage["model"] == "claude-model"
    assert usage["input_tokens"] == 7
    assert usage["output_tokens"] == 3
    assert isinstance(cache_read, int)
    assert isinstance(cache_creation, int)
    log_llm_call.assert_called_once_with(
        purpose="complete_text",
        model="claude-model",
        input_tokens=7,
        output_tokens=3,
        duration_s=1.25,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        stop_reason="end_turn",
        tool_calls=2,
    )


def test_log_and_build_usage_omits_tool_calls_when_not_provided(monkeypatch) -> None:
    response = SimpleNamespace(
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=4, output_tokens=1),
    )
    log_llm_call = MagicMock()
    monkeypatch.setattr(
        "praviar_pipeline.clients.claude_runtime_results.log_llm_call", log_llm_call
    )

    log_and_build_usage(
        purpose="thinking:ResponseModel",
        response=response,
        model="claude-model",
        total_input=4,
        total_output=1,
        duration_s=0.5,
    )

    assert "tool_calls" not in log_llm_call.call_args.kwargs

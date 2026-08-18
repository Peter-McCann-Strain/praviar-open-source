from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praviar_pipeline.agents.base_runtime import (
    build_research_loop_state,
    compute_effective_max_rounds,
    execute_research_loop,
    finalize_research_trace,
    prepare_research_round,
    record_research_round,
    should_warn_about_context_budget,
)
from praviar_pipeline.models.reasoning import ToolCall


def test_build_research_loop_state_initializes_trace() -> None:
    state = build_research_loop_state(
        agent_type="claim_analysis",
        model_id="claude-haiku",
        patent_id="US123",
        user_message="Investigate",
    )

    assert state.scratchpad == {}
    assert state.messages == [{"role": "user", "content": "Investigate"}]
    assert state.trace.agent_type == "claim_analysis"
    assert state.trace.model == "claude-haiku"
    assert state.trace.patent_id == "US123"


def test_compute_effective_rounds_and_budget_gate() -> None:
    assert compute_effective_max_rounds(5, 3) == 3
    assert should_warn_about_context_budget(90_001, 1) is True
    assert should_warn_about_context_budget(90_001, 0) is False


def test_prepare_research_round_uses_agent_hooks() -> None:
    state = build_research_loop_state(
        agent_type="test",
        model_id="model",
        patent_id="US1",
        user_message="task",
    )
    state.messages.append(
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "old"}],
        }
    )

    agent = SimpleNamespace(
        _build_system_prompt=lambda scratchpad: f"system:{scratchpad}",
        _build_cached_system_content=lambda scratchpad: [{"type": "text", "text": "cached"}],
        _mask_old_tool_outputs=lambda messages: messages,
        _round_instruction=lambda round_num, max_rounds, is_final: (
            f"{round_num}/{max_rounds}:{is_final}"
        ),
    )

    preparation = prepare_research_round(agent, state, round_number=1, max_rounds=3)

    assert preparation.system_prompt == "system:{}"
    assert preparation.cached_system == [{"type": "text", "text": "cached"}]
    assert preparation.round_instruction == "1/3:False"
    assert preparation.is_final_round is False
    assert preparation.context_chars > 0


def test_record_and_finalize_research_round() -> None:
    state = build_research_loop_state(
        agent_type="test",
        model_id="model",
        patent_id="US1",
        user_message="task",
    )

    record_research_round(
        state,
        round_number=0,
        thinking="reasoning" * 100,
        round_tool_calls=[ToolCall(tool_name="lookup")],
        round_text="final analysis" * 50,
        round_input_tokens=10,
        round_output_tokens=5,
        is_final_round=True,
    )
    trace = finalize_research_trace(state, 1234)

    assert state.total_input_tokens == 10
    assert state.total_output_tokens == 5
    assert state.final_text.startswith("final analysis")
    assert trace.total_duration_ms == 1234
    assert trace.rounds[0].decision == "final_output"
    assert len(trace.rounds[0].thinking_summary) == 500


@pytest.mark.asyncio
async def test_execute_research_loop_smoke_no_toolkit() -> None:
    claude = SimpleNamespace(
        complete_text=AsyncMock(
            return_value=("final answer", {"input_tokens": 11, "output_tokens": 7})
        )
    )
    agent = SimpleNamespace(
        _claude=claude,
        _settings=SimpleNamespace(
            agentic_max_agent_rounds=1,
            agentic_observation_masking=True,
            agentic_scratchpad_enabled=True,
            analysis_max_tokens=256,
        ),
        agent_type="test_agent",
        model_id="claude-haiku",
        max_rounds=1,
        build_toolkit=lambda context: None,
        format_task=lambda task, context: f"Research task: {task}",
        _build_system_prompt=lambda scratchpad: "system prompt",
        _build_cached_system_content=lambda scratchpad: [{"type": "text", "text": "system"}],
        _mask_old_tool_outputs=lambda messages: messages,
        _estimate_context_size=lambda messages: 12,
        _round_instruction=lambda round_num, max_rounds, is_final: "final instruction",
        _self_critique=AsyncMock(return_value=""),
    )

    final_text, trace = await execute_research_loop(agent, "Investigate", {"patent_id": "US123"})

    assert final_text == "final answer"
    assert len(trace.rounds) == 1
    assert trace.total_input_tokens == 11
    assert trace.total_output_tokens == 7

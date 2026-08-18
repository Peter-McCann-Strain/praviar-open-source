"""Helper functions for research-agent loop orchestration and state."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog

from praviar_pipeline.agents.base_helpers import estimate_context_size
from praviar_pipeline.agents.base_loop_helpers import (
    build_agent_round,
    extract_round_artifacts,
    serialize_message_content,
    serialize_response_content,
    should_append_response,
)
from praviar_pipeline.models.reasoning import ReasoningTrace

logger = structlog.get_logger()

# Maximum active tokens before aggressive masking
_CONTEXT_BUDGET_CHARS = 90_000  # ~30K tokens ≈ 90K chars


@dataclass
class ResearchLoopState:
    """Mutable execution state for a research-agent run."""

    scratchpad: dict[str, Any]
    messages: list[dict[str, Any]]
    trace: ReasoningTrace
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    final_text: str = ""


@dataclass
class ResearchRoundPreparation:
    """Deterministic inputs prepared for a single research round."""

    round_number: int
    is_final_round: bool
    system_prompt: str
    cached_system: list[dict[str, Any]]
    round_instruction: str
    context_chars: int


def compute_effective_max_rounds(max_rounds: int, agentic_max_agent_rounds: int) -> int:
    """Return the configured round limit for the current run."""
    return min(max_rounds, agentic_max_agent_rounds)


def build_research_loop_state(
    *,
    agent_type: str,
    model_id: str,
    patent_id: str,
    user_message: str,
) -> ResearchLoopState:
    """Create the initial mutable state for a research-agent run."""
    return ResearchLoopState(
        scratchpad={},
        messages=[{"role": "user", "content": user_message}],
        trace=ReasoningTrace(
            agent_type=agent_type,
            model=model_id,
            patent_id=patent_id,
        ),
    )


def prepare_research_round(
    agent: Any,
    state: ResearchLoopState,
    round_number: int,
    max_rounds: int,
) -> ResearchRoundPreparation:
    """Prepare prompt state for a single research round."""
    is_final_round = round_number == max_rounds - 1
    system_prompt = agent._build_system_prompt(state.scratchpad)
    cached_system = agent._build_cached_system_content(state.scratchpad)
    state.messages = agent._mask_old_tool_outputs(state.messages)
    context_chars = estimate_context_size(state.messages)
    round_instruction = agent._round_instruction(round_number, max_rounds, is_final_round)
    return ResearchRoundPreparation(
        round_number=round_number,
        is_final_round=is_final_round,
        system_prompt=system_prompt,
        cached_system=cached_system,
        round_instruction=round_instruction,
        context_chars=context_chars,
    )


def should_warn_about_context_budget(context_chars: int, round_number: int) -> bool:
    """Return True when the conversation has grown beyond the safety budget."""
    return context_chars > _CONTEXT_BUDGET_CHARS and round_number > 0


def record_research_round(
    state: ResearchLoopState,
    *,
    round_number: int,
    thinking: str,
    round_tool_calls: list[Any],
    round_text: str,
    round_input_tokens: int,
    round_output_tokens: int,
    is_final_round: bool,
) -> None:
    """Persist a completed research round into the loop state."""
    state.total_input_tokens += round_input_tokens
    state.total_output_tokens += round_output_tokens
    state.final_text = round_text
    state.trace.rounds.append(
        build_agent_round(
            round_number=round_number + 1,
            thinking=thinking,
            tool_calls=round_tool_calls,
            observations=round_text,
            is_final_round=is_final_round,
        )
    )


def finalize_research_trace(state: ResearchLoopState, total_duration_ms: int) -> ReasoningTrace:
    """Write the final execution totals back to the trace."""
    state.trace.total_input_tokens = state.total_input_tokens
    state.trace.total_output_tokens = state.total_output_tokens
    state.trace.total_duration_ms = total_duration_ms
    return state.trace


async def execute_research_loop(
    agent: Any,
    task: str,
    context: dict[str, Any],
) -> tuple[str, ReasoningTrace]:
    """Execute the deterministic research loop around the agent's Claude calls."""
    t0 = time.monotonic()
    toolkit = agent.build_toolkit(context)
    user_message = agent.format_task(task, context)
    effective_max_rounds = compute_effective_max_rounds(
        agent.max_rounds,
        agent._settings.agentic_max_agent_rounds,
    )
    state = build_research_loop_state(
        agent_type=agent.agent_type,
        model_id=agent.model_id,
        patent_id=context.get("patent_id", ""),
        user_message=user_message,
    )

    logger.info(
        "research_agent_start",
        agent_type=agent.agent_type,
        model=agent.model_id,
        max_rounds=effective_max_rounds,
        has_toolkit=toolkit is not None,
    )

    for round_number in range(effective_max_rounds):
        round_t0 = time.monotonic()
        preparation = prepare_research_round(agent, state, round_number, effective_max_rounds)

        if should_warn_about_context_budget(preparation.context_chars, round_number):
            logger.warning(
                "context_budget_exceeded",
                agent_type=agent.agent_type,
                round=round_number + 1,
                context_chars=preparation.context_chars,
                budget_chars=_CONTEXT_BUDGET_CHARS,
            )

        if toolkit and not preparation.is_final_round:
            response, round_input, round_output, thinking = await agent._claude._tool_use_loop(
                model=agent.model_id,
                max_tokens=agent._settings.analysis_max_tokens,
                system=preparation.cached_system,
                messages=state.messages,
                toolkit=toolkit,
                temperature=0.0,
                max_rounds=1,
                role="agent",
            )
        else:
            if round_number > 0:
                state.messages.append({"role": "user", "content": preparation.round_instruction})

            text, usage = await agent._claude.complete_text(
                system=preparation.system_prompt,
                user=serialize_message_content(state.messages[-1]["content"]),
                model=agent.model_id,
                max_tokens=agent._settings.analysis_max_tokens,
                cache_system=True,
                toolkit=toolkit if not preparation.is_final_round else None,
                role="agent",
            )
            round_input = usage["input_tokens"]
            round_output = usage["output_tokens"]
            thinking = ""
            response = None
            state.final_text = text

        round_text = state.final_text
        round_tool_calls: list[Any] = []
        if response is not None:
            round_text, round_tool_calls = extract_round_artifacts(response)
            state.final_text = round_text

        round_duration_ms = int((time.monotonic() - round_t0) * 1000)
        record_research_round(
            state,
            round_number=round_number,
            thinking=thinking,
            round_tool_calls=round_tool_calls,
            round_text=round_text,
            round_input_tokens=round_input,
            round_output_tokens=round_output,
            is_final_round=preparation.is_final_round,
        )

        logger.info(
            "research_round_complete",
            agent_type=agent.agent_type,
            round=round_number + 1,
            tool_calls=len(round_tool_calls),
            output_length=len(round_text),
            round_input_tokens=round_input,
            round_output_tokens=round_output,
            duration_ms=round_duration_ms,
        )

        if not round_tool_calls and round_text:
            break

        if should_append_response(response):
            state.messages.append(
                {
                    "role": "assistant",
                    "content": serialize_response_content(response.content),
                }
            )

    if len(state.trace.rounds) > 1 and state.final_text:
        critique = await agent._self_critique(state.final_text, context)
        state.trace.self_critique = critique

    total_duration_ms = int((time.monotonic() - t0) * 1000)
    finalize_research_trace(state, total_duration_ms)

    logger.info(
        "research_agent_complete",
        agent_type=agent.agent_type,
        rounds=len(state.trace.rounds),
        total_input_tokens=state.total_input_tokens,
        total_output_tokens=state.total_output_tokens,
        duration_ms=total_duration_ms,
        has_self_critique=bool(state.trace.self_critique),
    )

    return state.final_text, state.trace

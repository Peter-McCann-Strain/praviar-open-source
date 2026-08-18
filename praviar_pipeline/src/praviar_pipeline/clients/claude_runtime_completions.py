"""Claude completion helpers."""

from __future__ import annotations

import time

from praviar_pipeline.clients.claude_budget import (
    forfeit_claude_call,
    reserve_claude_call,
    settle_claude_call,
)
from praviar_pipeline.clients.claude_prompting import (
    build_effective_system,
    build_system_content,
)
from praviar_pipeline.clients.claude_response_cache import wrap_llm_call
from praviar_pipeline.clients.claude_responses import (
    response_text,
    tool_call_count,
)
from praviar_pipeline.clients.claude_runtime_completion_helpers import (
    execute_text_request,
    execute_thinking_request,
    validate_thinking_response,
)
from praviar_pipeline.clients.claude_runtime_helpers import (
    build_adaptive_thinking_config,
    build_stream_kwargs,
    build_thinking_config,
    model_supports_adaptive_thinking,
)
from praviar_pipeline.clients.claude_runtime_results import log_and_build_usage


async def complete_impl(
    *,
    client,
    models,
    system: str,
    user: str,
    response_model,
    log_fn,
    model: str | None = None,
    max_tokens: int = 8192,
    temperature: float = 0.0,
    effort: str | None = None,
    cache_system: bool = False,
    role: str = "unknown",
) -> tuple[object, dict]:
    """Implementation for ClaudeClient.complete.

    Transparently cache-aware: when a ``ResponseCache`` is installed,
    recording mode saves the parsed output + usage to disk; replay mode
    returns the cached result without contacting Anthropic.
    """
    model = model or models.analysis
    effective_system = build_effective_system(system)

    async def _live() -> tuple[object, dict]:
        system_content = build_system_content(effective_system, cache_system=cache_system)
        t0 = time.monotonic()
        kwargs = build_stream_kwargs(
            model=model,
            max_tokens=max_tokens,
            system=system_content,
            messages=[{"role": "user", "content": user}],
            response_model=response_model,
            thinking=(
                {"type": "adaptive"}
                if effort is not None and model_supports_adaptive_thinking(model)
                else None
            ),
            temperature=(
                temperature
                if effort is None or not model_supports_adaptive_thinking(model)
                else None
            ),
        )

        reservation = reserve_claude_call(
            model=model,
            max_output_tokens=max_tokens,
            prompt_components=(
                system_content,
                kwargs["messages"],
                kwargs.get("output_format"),
            ),
        )
        try:
            async with client.messages.stream(**kwargs) as stream:
                response = await stream.get_final_message()
        except BaseException:
            forfeit_claude_call(reservation)
            raise
        settle_claude_call(reservation, response=response, model=model)
        duration = time.monotonic() - t0

        usage, _, _ = log_and_build_usage(
            purpose=f"complete:{response_model.__name__}",
            response=response,
            model=model,
            total_input=response.usage.input_tokens,
            total_output=response.usage.output_tokens,
            duration_s=duration,
            log_fn=log_fn,
            role=role,
        )
        return response.parsed_output, usage

    parsed, usage, _extras = await wrap_llm_call(
        kind="complete",
        role=role,
        model=model,
        system=effective_system,
        user=user,
        response_model=response_model,
        max_tokens=max_tokens,
        temperature=temperature,
        effort=effort,
        cache_system=cache_system,
        live_call=_live,
        unwrap=lambda r: (r[0], r[1], {}),
    )
    return parsed, usage


async def complete_text_impl(
    *,
    client,
    models,
    system: str,
    user: str,
    log_fn,
    model: str | None = None,
    max_tokens: int = 8192,
    temperature: float = 0.0,
    effort: str | None = None,
    toolkit=None,
    cache_system: bool = False,
    max_rounds: int = 3,
    tool_use_loop=None,
    role: str = "unknown",
) -> tuple[str, dict]:
    """Implementation for ClaudeClient.complete_text."""
    model = model or models.analysis
    effective_system = build_effective_system(system)

    async def _live() -> tuple[str, dict]:
        system_content = build_system_content(effective_system, cache_system=cache_system)
        thinking_config = (
            build_adaptive_thinking_config(effort)
            if model_supports_adaptive_thinking(model)
            else None
        )
        messages = [{"role": "user", "content": user}]
        t0 = time.monotonic()

        response, total_input, total_output = await execute_text_request(
            client=client,
            model=model,
            max_tokens=max_tokens,
            system_content=system_content,
            messages=messages,
            thinking_config=thinking_config,
            temperature=temperature,
            toolkit=toolkit,
            max_rounds=max_rounds,
            tool_use_loop=tool_use_loop,
        )
        duration = time.monotonic() - t0
        text = response_text(response.content)
        usage, _, _ = log_and_build_usage(
            purpose="complete_text",
            response=response,
            model=model,
            total_input=total_input,
            total_output=total_output,
            duration_s=duration,
            tool_calls=tool_call_count(response.content) if response else 0,
            log_fn=log_fn,
            role=role,
        )
        return text, usage

    parsed, usage, _extras = await wrap_llm_call(
        kind="complete_text",
        role=role,
        model=model,
        system=effective_system,
        user=user,
        response_model=None,
        max_tokens=max_tokens,
        temperature=temperature,
        effort=effort,
        cache_system=cache_system,
        live_call=_live,
        unwrap=lambda r: (r[0], r[1], {}),
    )
    return parsed, usage


async def complete_with_thinking_impl(
    *,
    client,
    models,
    system: str,
    user: str,
    response_model,
    logger,
    log_fn,
    model: str | None = None,
    max_tokens: int = 128000,
    budget_tokens: int = 32000,
    json_schema: dict | None = None,
    toolkit=None,
    effort: str | None = None,
    cache_system: bool = False,
    max_rounds: int = 3,
    tool_use_loop=None,
    role: str = "unknown",
) -> tuple[object, str, dict]:
    """Implementation for ClaudeClient.complete_with_thinking.

    Transparently cache-aware: when a ``ResponseCache`` is installed,
    recording saves ``(parsed, thinking_text, usage)`` to disk; replay
    returns them without spending on the 32K-thinking round trip.
    """
    model = model or models.deep
    effective_system = build_effective_system(system, json_schema)

    async def _live() -> tuple[object, str, dict]:
        system_content = build_system_content(effective_system, cache_system=cache_system)
        messages = [{"role": "user", "content": user}]
        thinking_config = (
            build_thinking_config(effort, budget_tokens)
            if model_supports_adaptive_thinking(model)
            else None
        )

        t0 = time.monotonic()
        (
            response,
            thinking_text,
            result_text,
            total_input,
            total_output,
        ) = await execute_thinking_request(
            client=client,
            model=model,
            max_tokens=max_tokens,
            system_content=system_content,
            messages=messages,
            thinking_config=thinking_config,
            toolkit=toolkit,
            max_rounds=max_rounds,
            tool_use_loop=tool_use_loop,
        )

        duration = time.monotonic() - t0
        usage, cache_read, cache_creation = log_and_build_usage(
            purpose=f"thinking:{response_model.__name__}",
            response=response,
            model=model,
            total_input=total_input,
            total_output=total_output,
            duration_s=duration,
            log_fn=log_fn,
            role=role,
        )
        parsed = validate_thinking_response(
            response_model=response_model,
            result_text=result_text,
            thinking_text=thinking_text,
            model=model,
            budget_tokens=budget_tokens,
            stop_reason=response.stop_reason or "",
            logger=logger.bind(
                cache_read_tokens=cache_read,
                cache_creation_tokens=cache_creation,
            ),
        )
        return parsed, thinking_text, usage

    parsed, usage, extras = await wrap_llm_call(
        kind="complete_with_thinking",
        role=role,
        model=model,
        system=effective_system,
        user=user,
        response_model=response_model,
        max_tokens=max_tokens,
        temperature=0.0,
        effort=effort,
        cache_system=cache_system,
        budget_tokens=budget_tokens,
        live_call=_live,
        unwrap=lambda r: (r[0], r[2], {"thinking_text": r[1]}),
    )
    return parsed, extras.get("thinking_text", ""), usage

"""Execution helpers for Claude runtime completion paths."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from praviar_pipeline.clients.claude_budget import (
    forfeit_claude_call,
    reserve_claude_call,
    settle_claude_call,
)
from praviar_pipeline.clients.claude_prompting import extract_json
from praviar_pipeline.clients.claude_responses import latest_thinking_text, response_text
from praviar_pipeline.clients.claude_runtime_helpers import build_stream_kwargs
from praviar_pipeline.errors import LLMResponseError

T = TypeVar("T", bound=BaseModel)


async def execute_text_request(
    *,
    client,
    model: str,
    max_tokens: int,
    system_content: str | list,
    messages: list[dict],
    thinking_config: dict | None,
    temperature: float,
    toolkit: Any | None,
    max_rounds: int,
    tool_use_loop,
) -> tuple[Any, int, int]:
    """Execute the plain-text Claude request, with optional tool use."""
    if toolkit:
        response, total_input, total_output, _ = await tool_use_loop(
            client=client,
            max_rounds=max_rounds,
            model=model,
            max_tokens=max_tokens,
            system=system_content,
            messages=messages,
            toolkit=toolkit,
            thinking=thinking_config,
            temperature=temperature,
        )
        return response, total_input, total_output

    kwargs = build_stream_kwargs(
        model=model,
        max_tokens=max_tokens,
        system=system_content,
        messages=messages,
        thinking=thinking_config,
        temperature=temperature if thinking_config is None else None,
    )

    reservation = reserve_claude_call(
        model=model,
        max_output_tokens=max_tokens,
        prompt_components=(system_content, messages),
    )
    try:
        async with client.messages.stream(**kwargs) as stream:
            response = await stream.get_final_message()
    except BaseException:
        forfeit_claude_call(reservation)
        raise
    settle_claude_call(reservation, response=response, model=model)
    return response, response.usage.input_tokens, response.usage.output_tokens


async def execute_thinking_request(
    *,
    client,
    model: str,
    max_tokens: int,
    system_content: str | list,
    messages: list[dict],
    thinking_config: dict | None,
    toolkit: Any | None,
    max_rounds: int,
    tool_use_loop,
) -> tuple[Any, str, str, int, int]:
    """Execute the extended-thinking Claude request, with optional tool use."""
    if toolkit:
        response, total_input, total_output, thinking_text = await tool_use_loop(
            client=client,
            max_rounds=max_rounds,
            model=model,
            max_tokens=max_tokens,
            system=system_content,
            messages=messages,
            toolkit=toolkit,
            thinking=thinking_config,
        )
        return response, thinking_text, response_text(response.content), total_input, total_output

    kwargs = build_stream_kwargs(
        model=model,
        max_tokens=max_tokens,
        system=system_content,
        messages=messages,
        thinking=thinking_config,
    )
    reservation = reserve_claude_call(
        model=model,
        max_output_tokens=max_tokens,
        prompt_components=(system_content, messages),
    )
    try:
        async with client.messages.stream(**kwargs) as stream:
            response = await stream.get_final_message()
    except BaseException:
        forfeit_claude_call(reservation)
        raise
    settle_claude_call(reservation, response=response, model=model)

    return (
        response,
        latest_thinking_text(response.content),
        response_text(response.content),
        response.usage.input_tokens,
        response.usage.output_tokens,
    )


def validate_thinking_response(
    *,
    response_model: type[T],
    result_text: str,
    thinking_text: str,
    model: str,
    budget_tokens: int,
    logger,
    stop_reason: str = "",
) -> T:
    """Extract and validate structured JSON from the thinking completion text."""
    if stop_reason == "max_tokens":
        raise LLMResponseError(
            f"Response truncated by max_tokens limit before JSON was complete "
            f"(model={model}, budget={budget_tokens})"
        )
    json_text = extract_json(result_text)
    logger.debug(
        "thinking_extraction",
        response_model=response_model.__name__,
        raw_text_length=len(result_text),
        extracted_json_length=len(json_text),
        thinking_length=len(thinking_text),
        budget_tokens=budget_tokens,
    )

    validation_failure_type: str | None = None
    try:
        parsed = response_model.model_validate_json(json_text)
        logger.debug(
            "thinking_json_parse_success",
            response_model=response_model.__name__,
            extracted_length=len(json_text),
        )
        return parsed
    except ValidationError as exc:
        validation_failure_type = type(exc).__name__
        logger.error(
            "thinking_json_parse_failed",
            model=model,
            response_model=response_model.__name__,
            raw_length=len(result_text),
            extracted_length=len(json_text),
            error_type=validation_failure_type,
        )
    if validation_failure_type is not None:
        raise LLMResponseError(
            "Structured response validation failed",
            model=model,
            step="completion_validation",
        ) from None
    raise AssertionError("thinking response validation reached an unreachable state")

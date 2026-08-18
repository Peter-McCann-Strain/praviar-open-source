"""Runtime helpers for the Claude client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

import anthropic
import httpx
import structlog
from pydantic import BaseModel

from praviar_pipeline.clients.claude_runtime_completions import (
    complete_impl as _complete_impl,
)
from praviar_pipeline.clients.claude_runtime_completions import (
    complete_text_impl as _complete_text_impl,
)
from praviar_pipeline.clients.claude_runtime_completions import (
    complete_with_thinking_impl as _complete_with_thinking_impl,
)
from praviar_pipeline.clients.claude_runtime_helpers import (
    build_claude_transport_impl,
)
from praviar_pipeline.clients.claude_runtime_tool_loop import (
    tool_use_loop_impl as _tool_use_loop_impl,
)
from praviar_pipeline.logging_config import log_llm_call

if TYPE_CHECKING:
    from praviar_pipeline.config_models import ClaudeModels

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


def build_claude_transport(
    settings,
    *,
    anthropic_module=anthropic,
    httpx_module=httpx,
) -> tuple[anthropic.AsyncAnthropic, ClaudeModels]:
    """Build the Anthropic transport and model bundle from settings."""
    return cast(
        "tuple[anthropic.AsyncAnthropic, ClaudeModels]",
        build_claude_transport_impl(
            settings,
            anthropic_module=anthropic_module,
            httpx_module=httpx_module,
        ),
    )


async def tool_use_loop_impl(
    *,
    client: anthropic.AsyncAnthropic,
    max_rounds: int,
    model: str,
    max_tokens: int,
    system: str | list,
    messages: list[dict],
    toolkit: Any,
    thinking: dict | None = None,
    temperature: float | None = 0.0,
    role: str | None = None,
) -> tuple[Any, int, int, str]:
    """Execute the Claude tool loop until a final response is produced.

    Defaults ``temperature`` to ``0.0`` for reproducibility; callers can pass
    an explicit value when sampling diversity is genuinely required.

    ``role`` is forwarded to the inner impl. Leave unset when the caller
    wraps the loop in ``log_and_build_usage`` (avoids double-counting); pass
    a role string when the loop's tokens would otherwise go untracked
    (e.g. ``role="agent"`` for the research-agent path).
    """
    return await _tool_use_loop_impl(
        client=client,
        max_rounds=max_rounds,
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        toolkit=toolkit,
        logger=logger,
        thinking=thinking,
        temperature=temperature,
        role=role,
    )


async def complete_impl(
    *,
    client: anthropic.AsyncAnthropic,
    models: ClaudeModels,
    system: str,
    user: str,
    response_model: type[T],
    model: str | None = None,
    max_tokens: int = 8192,
    temperature: float = 0.0,
    effort: str | None = None,
    cache_system: bool = False,
    role: str = "unknown",
) -> tuple[T, dict]:
    """Implementation for ClaudeClient.complete."""
    return cast(
        "tuple[T, dict]",
        await _complete_impl(
            client=client,
            models=models,
            system=system,
            user=user,
            response_model=response_model,
            log_fn=log_llm_call,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            effort=effort,
            cache_system=cache_system,
            role=role,
        ),
    )


async def complete_text_impl(
    *,
    client: anthropic.AsyncAnthropic,
    models: ClaudeModels,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 8192,
    temperature: float = 0.0,
    effort: str | None = None,
    toolkit: Any | None = None,
    cache_system: bool = False,
    max_rounds: int = 3,
    tool_use_loop: Any = tool_use_loop_impl,
    role: str = "unknown",
) -> tuple[str, dict]:
    """Implementation for ClaudeClient.complete_text."""
    return await _complete_text_impl(
        client=client,
        models=models,
        system=system,
        user=user,
        log_fn=log_llm_call,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        effort=effort,
        toolkit=toolkit,
        cache_system=cache_system,
        max_rounds=max_rounds,
        tool_use_loop=tool_use_loop,
        role=role,
    )


async def complete_with_thinking_impl(
    *,
    client: anthropic.AsyncAnthropic,
    models: ClaudeModels,
    system: str,
    user: str,
    response_model: type[T],
    model: str | None = None,
    max_tokens: int = 128000,
    budget_tokens: int = 32000,
    json_schema: dict | None = None,
    toolkit: Any | None = None,
    effort: str | None = None,
    cache_system: bool = False,
    max_rounds: int = 3,
    tool_use_loop: Any = tool_use_loop_impl,
    role: str = "unknown",
) -> tuple[T, str, dict]:
    """Implementation for ClaudeClient.complete_with_thinking."""
    return cast(
        "tuple[T, str, dict]",
        await _complete_with_thinking_impl(
            client=client,
            models=models,
            system=system,
            user=user,
            response_model=response_model,
            logger=logger,
            log_fn=log_llm_call,
            model=model,
            max_tokens=max_tokens,
            budget_tokens=budget_tokens,
            json_schema=json_schema,
            toolkit=toolkit,
            effort=effort,
            cache_system=cache_system,
            max_rounds=max_rounds,
            tool_use_loop=tool_use_loop,
            role=role,
        ),
    )

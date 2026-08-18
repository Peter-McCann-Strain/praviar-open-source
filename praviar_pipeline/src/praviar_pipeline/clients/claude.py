"""Anthropic Claude API client — structured LLM calls for the FTO pipeline."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

import anthropic
import httpx
from pydantic import BaseModel

from praviar_pipeline.clients import claude_runtime as _claude_runtime
from praviar_pipeline.clients.base import AsyncClientMixin
from praviar_pipeline.clients.claude_prompting import (
    current_date_context as _current_date_context,
)
from praviar_pipeline.clients.claude_prompting import (
    extract_json as _extract_json,
)
from praviar_pipeline.clients.claude_prompting import (
    load_prompt as _load_prompt,
)
from praviar_pipeline.clients.claude_prompting import (
    repair_truncated_json as _repair_truncated_json,
)
from praviar_pipeline.clients.claude_runtime import (
    build_claude_transport,
    complete_impl,
    complete_text_impl,
    complete_with_thinking_impl,
    tool_use_loop_impl,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.no_paid_api import PaidApiBlockedError, assert_paid_api_allowed

__all__ = [
    "ClaudeClient",
    "PaidApiBlockedError",
    "Toolkit",
    "_current_date_context",
    "_extract_json",
    "_load_prompt",
    "_repair_truncated_json",
]


@runtime_checkable
class Toolkit(Protocol):
    """Protocol for any toolkit that can be used with ClaudeClient tool use."""

    @property
    def tool_definitions(self) -> list[dict[str, Any]]: ...

    async def execute(self, tool_name: str, tool_input: dict) -> str: ...


T = TypeVar("T", bound=BaseModel)


class ClaudeClient(AsyncClientMixin):
    """Async Claude API client with structured output support."""

    def __init__(self) -> None:
        assert_paid_api_allowed("Anthropic")
        _claude_runtime.anthropic = anthropic
        _claude_runtime.httpx = httpx
        self._client, self._models = build_claude_transport(get_settings())

    async def _tool_use_loop(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str | list,
        messages: list[dict],
        toolkit: Toolkit,
        thinking: dict | None = None,
        temperature: float | None = 0.0,
        max_rounds: int | None = None,
        role: str | None = None,
    ) -> tuple[Any, int, int, str]:
        """Execute streaming tool use loop until model produces final output.

        ``temperature`` defaults to ``0.0`` to keep multi-turn analysis and
        verification reproducible. Pass an explicit value (or ``None``, which
        falls back to the API default) only for paths that require sampling
        diversity (e.g. GEPA prompt evolution).

        ``role`` opts the loop into per-run cost tracking. Leave it unset
        when the caller separately reports usage via ``log_and_build_usage``;
        pass a role (e.g. ``"agent"``) on the direct-driver paths so the
        cost tracker captures their tokens.
        """
        settings = get_settings()
        return await tool_use_loop_impl(
            client=self._client,
            max_rounds=max_rounds if max_rounds is not None else settings.max_tool_rounds,
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            toolkit=toolkit,
            thinking=thinking,
            temperature=temperature,
            role=role,
        )

    async def complete(
        self,
        *,
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
        """Make a structured output call to Claude.

        ``role`` tags the call for the per-run cost tracker
        (:mod:`praviar_pipeline.cost_tracker`). Defaults to ``"unknown"`` — the
        hot-path callers (triage, analysis, DoE, invalidity, verification,
        report, critic) pass their own role so the cost breakdown is usable.
        """
        return await complete_impl(
            client=self._client,
            models=self._models,
            system=system,
            user=user,
            response_model=response_model,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            effort=effort,
            cache_system=cache_system,
            role=role,
        )

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        effort: str | None = None,
        toolkit: Toolkit | None = None,
        cache_system: bool = False,
        role: str = "unknown",
        max_rounds: int | None = None,
    ) -> tuple[str, dict]:
        """Make a plain text call to Claude (no structured output)."""
        return await complete_text_impl(
            client=self._client,
            models=self._models,
            system=system,
            user=user,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            effort=effort,
            toolkit=toolkit,
            cache_system=cache_system,
            max_rounds=(max_rounds if max_rounds is not None else get_settings().max_tool_rounds),
            tool_use_loop=tool_use_loop_impl,
            role=role,
        )

    async def complete_with_thinking(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
        model: str | None = None,
        max_tokens: int = 128000,
        budget_tokens: int = 32000,
        json_schema: dict | None = None,
        toolkit: Toolkit | None = None,
        effort: str | None = None,
        cache_system: bool = False,
        role: str = "unknown",
    ) -> tuple[T, str, dict]:
        """Make a structured output call with extended thinking enabled."""
        return await complete_with_thinking_impl(
            client=self._client,
            models=self._models,
            system=system,
            user=user,
            response_model=response_model,
            model=model,
            max_tokens=max_tokens,
            budget_tokens=budget_tokens,
            json_schema=json_schema,
            toolkit=toolkit,
            effort=effort,
            cache_system=cache_system,
            max_rounds=get_settings().max_tool_rounds,
            tool_use_loop=tool_use_loop_impl,
            role=role,
        )

    def load_prompt(self, filename: str) -> str:
        """Load a prompt template from the prompts directory."""
        return _load_prompt(filename)

    async def close(self) -> None:
        await self._client.close()

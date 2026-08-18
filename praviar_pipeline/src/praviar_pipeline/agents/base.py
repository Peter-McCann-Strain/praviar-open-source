"""ResearchAgent — base class for multi-turn research agents using ReAct pattern.

Each research agent runs a think→act→observe loop, maintaining a structured
scratchpad and masking old tool outputs to stay within context budget.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
import structlog

from praviar_pipeline.agents.base_helpers import (
    MASKED_TOOL_OUTPUT_SENTINEL,
    build_cached_system_content,
    build_system_prompt,
    estimate_context_size,
    mask_old_tool_outputs,
    round_instruction,
)
from praviar_pipeline.agents.base_loop_helpers import build_critique_prompt
from praviar_pipeline.agents.base_runtime import execute_research_loop
from praviar_pipeline.clients.claude import (
    ClaudeClient,
    Toolkit,
    _current_date_context,
    _load_prompt,
)
from praviar_pipeline.config import get_settings
from praviar_pipeline.sanitize import UNTRUSTED_DATA_POLICY

logger = structlog.get_logger()

# Sentinel replacing masked tool outputs
_MASKED = MASKED_TOOL_OUTPUT_SENTINEL

# Maximum active tokens before aggressive masking
_CONTEXT_BUDGET_CHARS = 90_000  # ~30K tokens ≈ 90K chars

if TYPE_CHECKING:
    from praviar_pipeline.models.reasoning import ReasoningTrace


class ResearchAgent(ABC):
    """Base class for multi-turn research agents.

    Subclasses must implement:
        - agent_type: str property identifying this agent
        - model_id: str property for which Claude model to use
        - max_rounds: int property for max research rounds
        - prompt_file: str property for the system prompt filename
        - build_toolkit: method returning a Toolkit for this agent's tools
        - format_task: method formatting the research task as a user message
        - parse_output: method extracting structured results from agent output
    """

    def __init__(self, claude: ClaudeClient) -> None:
        self._claude = claude
        self._settings = get_settings()

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Identifier for this agent type (e.g. 'claim_analysis')."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Claude model ID to use for this agent."""

    @property
    @abstractmethod
    def max_rounds(self) -> int:
        """Maximum number of research rounds."""

    @property
    @abstractmethod
    def prompt_file(self) -> str:
        """Filename of the system prompt in prompts/ directory."""

    @abstractmethod
    def build_toolkit(self, context: dict[str, Any]) -> Toolkit | None:
        """Build the toolkit for this agent's research session.

        Args:
            context: Agent-specific context (e.g. patent data, compound info).

        Returns:
            Toolkit instance, or None if no tools needed.
        """

    @abstractmethod
    def format_task(self, task: str, context: dict[str, Any]) -> str:
        """Format the initial research task as a user message.

        Args:
            task: High-level task description.
            context: Agent-specific context.
        """

    def _build_system_prompt(self, scratchpad: dict[str, Any]) -> str:
        """Build system prompt with role, rules, and current scratchpad state."""
        base_prompt = (
            _current_date_context()
            + UNTRUSTED_DATA_POLICY
            + "\n\n"
            + _load_prompt(self.prompt_file)
        )
        return build_system_prompt(
            base_prompt=base_prompt,
            scratchpad=scratchpad,
            scratchpad_enabled=self._settings.agentic_scratchpad_enabled,
        )

    def _build_cached_system_content(self, scratchpad: dict[str, Any]) -> list:
        """Build system content with prompt caching for tool_use_loop calls.

        The static base prompt (instructions + date context) is marked for
        provider prompt caching. Pricing is intentionally not asserted here;
        the scratchpad changes each round and stays uncached.
        """
        base_prompt = (
            _current_date_context()
            + UNTRUSTED_DATA_POLICY
            + "\n\n"
            + _load_prompt(self.prompt_file)
        )
        return build_cached_system_content(
            base_prompt=base_prompt,
            scratchpad=scratchpad,
            scratchpad_enabled=self._settings.agentic_scratchpad_enabled,
        )

    def _mask_old_tool_outputs(self, messages: list[dict]) -> list[dict]:
        """Replace old tool outputs with summaries to stay within context budget.

        Keeps only the most recent round's tool results intact. Earlier rounds
        get their tool_result content replaced with _MASKED sentinel.
        """
        return mask_old_tool_outputs(
            messages,
            masking_enabled=self._settings.agentic_observation_masking,
            masked_sentinel=_MASKED,
        )

    def _estimate_context_size(self, messages: list[dict]) -> int:
        """Rough estimate of total context size in characters."""
        return estimate_context_size(messages)

    async def research(
        self,
        task: str,
        context: dict[str, Any],
    ) -> tuple[str, ReasoningTrace]:
        return await execute_research_loop(self, task, context)

    async def _self_critique(self, output: str, context: dict[str, Any]) -> str:
        """Ask the agent to critique its own analysis."""
        critique_prompt = build_critique_prompt(output)
        try:
            critique_text, _ = await self._claude.complete_text(
                system=(
                    "You are a senior patent attorney reviewing an FTO analysis. "
                    "Identify specific inconsistencies, missing considerations, "
                    "or logical errors. Be concise and actionable."
                ),
                user=critique_prompt,
                model=self._settings.claude_triage_model,  # Cheap model for critique
                max_tokens=2048,
                cache_system=True,  # Cache critique prompt across agents
            )
            return critique_text
        except (httpx.HTTPError, ConnectionError, TimeoutError, anthropic.APIError):
            logger.warning(
                "self_critique_failed",
                agent_type=self.agent_type,
            )
            return ""

    def _round_instruction(
        self,
        round_num: int,
        max_rounds: int,
        is_final: bool,
    ) -> str:
        """Generate per-round instruction text."""
        return round_instruction(round_num, max_rounds, is_final)

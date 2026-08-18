"""FTO analysis tools for Claude."""

from __future__ import annotations

from typing import Any

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.tools_cache import build_known_patent_cache
from praviar_pipeline.tools_definitions import TOOL_DEFINITIONS
from praviar_pipeline.tools_lookup import handle_get_current_date, handle_lookup_patent
from praviar_pipeline.tools_status import handle_check_patent_status

logger = structlog.get_logger()


class FTOToolkit:
    """Toolkit that provides tools to Claude during FTO analysis.

    Pre-populates a cache with known patent data to avoid redundant
    API calls. Unknown patents are looked up on-demand from BigQuery
    and USPTO.
    """

    def __init__(
        self,
        known_patents: dict[str, dict] | None = None,
        enabled_tools: list[str] | None = None,
    ) -> None:
        self._cache: dict[str, dict] = {}
        if known_patents:
            self._cache.update(known_patents)

        # Filter tool definitions if specific tools requested
        if enabled_tools:
            self._tool_defs = [t for t in TOOL_DEFINITIONS if t["name"] in enabled_tools]
        else:
            self._tool_defs = list(TOOL_DEFINITIONS)

        self._handlers = {
            "get_current_date": self._exec_get_current_date,
            "lookup_patent": self._exec_lookup_patent,
            "check_patent_status": self._exec_check_patent_status,
        }

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        """Tool definitions in Anthropic API format."""
        return self._tool_defs

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool by name, returning the result as a string.

        Never raises — returns error strings that the LLM can interpret.
        """
        handler = self._handlers.get(tool_name)
        if not handler:
            return f"Unknown tool: {tool_name}. Available: {list(self._handlers.keys())}"

        try:
            return await handler(tool_input)
        except Exception:
            logger.error(
                "tool_execution_error",
                tool=tool_name,
            )
            return f"Tool '{tool_name}' failed with a provider or validation error"

    async def _exec_get_current_date(self, input_data: dict) -> str:
        return await handle_get_current_date(input_data)

    async def _exec_lookup_patent(self, input_data: dict) -> str:
        return await handle_lookup_patent(input_data, self._cache)

    async def _exec_check_patent_status(self, input_data: dict) -> str:
        return await handle_check_patent_status(input_data, self._cache)

    @classmethod
    def from_patent_hits(
        cls,
        patents: list,
        enabled_tools: list[str] | None = None,
    ) -> FTOToolkit:
        """Create a toolkit pre-populated with PatentHit data.

        This avoids redundant BigQuery lookups for patents we already have.
        """
        settings = get_settings()
        known = build_known_patent_cache(
            patents,
            claims_truncation=settings.tool_claims_truncation,
        )
        return cls(known_patents=known, enabled_tools=enabled_tools)

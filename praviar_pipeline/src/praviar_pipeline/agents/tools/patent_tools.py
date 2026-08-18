"""Patent research tools — specification retrieval and definition search."""

from __future__ import annotations

import re
from typing import Any

import structlog

from praviar_pipeline.tools_definitions import TOOL_DEFINITIONS
from praviar_pipeline.utils.spec_text import chunk_spec_text

logger = structlog.get_logger()

_LOOKUP_PATENT_DEF = next(d for d in TOOL_DEFINITIONS if d["name"] == "lookup_patent")

# Per-call specification budget for the deep-research toolkit. Oversized
# specifications are reduced by definition-aware chunking rather than blunt
# truncation, so claim terms can still be construed against the passages that
# define them (Phillips v. AWH Corp.).
_MAX_SPEC_CHARS = 240_000
_MAX_DEFINITION_CHARS = 10_000


class PatentResearchToolkit:
    """Toolkit providing patent specification access for research agents.

    Tools:
        - fetch_specification: Get full patent description/specification text
        - search_spec_definitions: Search for term definitions in specification
        - lookup_patent: Get basic patent metadata (reuses cached data)
    """

    def __init__(self, patent_cache: dict[str, Any] | None = None) -> None:
        self._patent_cache = patent_cache or {}
        self._spec_cache: dict[str, str] = {}

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "fetch_specification",
                "description": (
                    "Fetch the full specification/description text of a patent from BigQuery. "
                    "Oversized specifications are reduced by definition-aware chunking, "
                    "preserving lexicographic definitions. Use this FIRST for every patent "
                    "before analysis."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "patent_id": {
                            "type": "string",
                            "description": "Patent publication number (e.g. US7851188B2)",
                        },
                    },
                    "required": ["patent_id"],
                },
            },
            {
                "name": "search_spec_definitions",
                "description": (
                    "Search the patent specification for definitions of a specific term. "
                    "Looks for patterns like 'as used herein', 'the term X means', "
                    "'X is defined as'. Returns relevant paragraphs."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "patent_id": {
                            "type": "string",
                            "description": "Patent publication number",
                        },
                        "term": {
                            "type": "string",
                            "description": "The claim term to search definitions for",
                        },
                    },
                    "required": ["patent_id", "term"],
                },
            },
            _LOOKUP_PATENT_DEF,
        ]

    async def execute(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool by name."""
        if tool_name == "fetch_specification":
            return await self._fetch_specification(tool_input["patent_id"])
        elif tool_name == "search_spec_definitions":
            return await self._search_definitions(
                tool_input["patent_id"],
                tool_input["term"],
            )
        elif tool_name == "lookup_patent":
            return self._lookup_patent(tool_input["patent_id"])
        else:
            return f"Unknown tool: {tool_name}"

    async def _fetch_specification(self, patent_id: str) -> str:
        """Fetch patent specification text from BigQuery."""
        # Check cache first
        if patent_id in self._spec_cache:
            return chunk_spec_text(self._spec_cache[patent_id], max_chars=_MAX_SPEC_CHARS)

        try:
            from praviar_pipeline.clients.bigquery import BigQueryClient

            async with BigQueryClient() as bq:
                text = await bq.get_patent_full_text(patent_id)

            if text:
                self._spec_cache[patent_id] = text
                return chunk_spec_text(text, max_chars=_MAX_SPEC_CHARS)
            return f"No specification text found for {patent_id}"

        except Exception:
            logger.warning(
                "spec_fetch_failed",
            )
            return "Specification retrieval failed with a provider or validation error"

    async def _search_definitions(self, patent_id: str, term: str) -> str:
        """Search specification for definitions of a claim term."""
        # Ensure we have the spec text
        if patent_id not in self._spec_cache:
            await self._fetch_specification(patent_id)

        spec_text = self._spec_cache.get(patent_id, "")
        if not spec_text:
            return f"No specification available for {patent_id}"

        # Search for definitional patterns
        term_lower = term.lower()
        patterns = [
            rf'(?i)as\s+used\s+herein[,]?\s+["\']?{re.escape(term_lower)}',
            rf'(?i)the\s+term\s+["\']?{re.escape(term_lower)}["\']?\s+(?:means|refers\s+to|is\s+defined)',
            rf'(?i)["\']?{re.escape(term_lower)}["\']?\s+(?:means|refers\s+to|is\s+defined\s+as|includes)',
            rf'(?i)by\s+["\']?{re.escape(term_lower)}["\']?\s+(?:we\s+mean|is\s+meant|it\s+is\s+meant)',
        ]

        found_paragraphs = []
        # Split into paragraphs and search
        paragraphs = spec_text.split("\n\n")
        for para in paragraphs:
            para_lower = para.lower()
            if term_lower in para_lower:
                for pattern in patterns:
                    if re.search(pattern, para):
                        found_paragraphs.append(para.strip())
                        break

        if not found_paragraphs:
            # Fallback: return any paragraph mentioning the term
            for para in paragraphs:
                if term_lower in para.lower() and len(para) > 50:
                    found_paragraphs.append(para.strip())
                    if len(found_paragraphs) >= 3:
                        break

        if found_paragraphs:
            result = f"Found {len(found_paragraphs)} relevant paragraph(s) for '{term}':\n\n"
            for i, para in enumerate(found_paragraphs[:5], 1):
                result += f"[{i}] {para[:600]}\n\n"
            return result[:_MAX_DEFINITION_CHARS]

        return f"No explicit definition found for '{term}' in the specification."

    def _lookup_patent(self, patent_id: str) -> str:
        """Look up patent metadata from cache."""
        if patent_id in self._patent_cache:
            data = self._patent_cache[patent_id]
            parts = [f"Patent: {patent_id}"]
            if isinstance(data, dict):
                for key in ["title", "abstract", "assignee", "filing_date", "grant_date"]:
                    if data.get(key):
                        val = str(data[key])
                        parts.append(f"{key}: {val[:500]}")
            return "\n".join(parts)

        return f"No cached data for {patent_id}. Use fetch_specification to retrieve full text."

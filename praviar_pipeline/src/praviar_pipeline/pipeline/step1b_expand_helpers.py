"""Helpers for Step 1.5 query expansion."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import ValidationError

from praviar_pipeline.clients.claude import _extract_json
from praviar_pipeline.errors import ConfigurationError, SourceUnavailableError
from praviar_pipeline.models.search import (
    ExpandedSearchQueries,
    ExpandedSearchQueryTerms,
    QueryExpansionProvenance,
)
from praviar_pipeline.pipeline.query_expansion_helpers import (
    build_no_search_prompt,
    build_search_agent_prompt,
    format_tavily_results,
)
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.clients.tavily import TavilyClient

logger = structlog.get_logger()

# CPC code format: letter, 2 digits, letter, then optional digits/slashes
_CPC_PATTERN = re.compile(r"^[A-HY]\d{2}[A-Z]\d{1,4}(?:/\d{1,6})?$")


def validate_cpc_code(code: str) -> bool:
    """Check if a CPC code has a valid format."""
    return bool(_CPC_PATTERN.match(code.strip()))


class ExpansionToolkit:
    """Minimal toolkit giving the LLM a Tavily web search tool."""

    def __init__(self, tavily_client: TavilyClient, *, required: bool = False) -> None:
        self._tavily = tavily_client
        self._required = required
        self.grounding_queries: list[str] = []
        self.source_urls: list[str] = []
        self.grounding_evidence: list[str] = []

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "web_search",
                "description": (
                    "Search the web for real, verified information about patent "
                    "classifications (CPC codes), company names that appear on "
                    "patent filings, and production methods. Use this to ground "
                    "your output in factual data rather than relying on memory. "
                    "You SHOULD call this tool 2-3 times with different queries "
                    "before generating your final output."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Search query. Be specific, e.g. "
                                "'succinic acid CPC patent classification code' or "
                                "'BioAmber succinic acid patent assignee'"
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute the web_search tool."""
        if tool_name != "web_search":
            return f"Unknown tool: {tool_name}. Available: ['web_search']"

        query = tool_input.get("query", "").strip()
        if not query:
            return "Error: query is required."

        results = await self._tavily.search(query, max_results=5, required=self._required)
        if not results:
            return "No results found. Try a different query."

        self.grounding_queries.append(query)
        self.source_urls.extend(
            str(result.get("url") or "").strip()
            for result in results
            if str(result.get("url") or "").strip()
        )
        formatted = format_tavily_results(results)
        self.grounding_evidence.append(formatted)
        return formatted


async def expand_with_search_agent(
    client: ClaudeClient,
    system_prompt: str,
    compound_context: str,
    tavily: TavilyClient,
    settings: Any,
) -> ExpandedSearchQueries:
    """Search agent pattern: LLM uses web_search tool, then generates JSON."""
    toolkit = ExpansionToolkit(
        tavily,
        required=query_expansion_requires_grounding(settings),
    )

    user_prompt = build_search_agent_prompt(compound_context)

    # First pass: tool use loop gathers web search results (free-form).
    text, usage = await client.complete_text(
        system=system_prompt,
        user=user_prompt,
        model=settings.claude_triage_model,
        toolkit=toolkit,
        max_tokens=2048,
        temperature=0.0,
        cache_system=True,
        role="expand",
        max_rounds=4,
    )

    logger.debug(
        "search_agent_raw_output",
        output_length=len(text),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )

    # Second pass: constrained decoding cannot produce invalid JSON.
    # First try to parse whatever the tool loop returned; if it's not clean
    # JSON (e.g. Haiku hit max_rounds and returned prose), fall back to a
    # fresh complete() call that uses the compound context alone.
    try:
        json_text = _extract_json(text)
        terms = ExpandedSearchQueryTerms.model_validate_json(json_text)
        result = ExpandedSearchQueries(**terms.model_dump())
    except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as exc:
        logger.warning(
            "search_agent_json_parse_failed_retrying_constrained",
            error_type=safe_exception_type(exc),
            grounding_required=query_expansion_requires_grounding(settings),
        )
        # Tool loop gathered web data — grounding is satisfied even if the prose
        # output wasn't valid JSON.  Feed the research prose back in as context
        # so constrained decoding can extract structured output from it.
        grounded_evidence = "\n\n".join([text, *toolkit.grounding_evidence]).strip()
        grounded_user = (
            "Extract grounded search queries from the supplied evidence.\n\n"
            + sanitize_untrusted_text(compound_context, data_type="compound_context")
            + "\n\n"
            + sanitize_untrusted_text(
                grounded_evidence,
                data_type="model_web_research_summary",
            )
        )
        terms, _ = await client.complete(
            system=system_prompt,
            user=grounded_user,
            response_model=ExpandedSearchQueryTerms,
            model=settings.claude_triage_model,
            max_tokens=2048,
            temperature=0.0,
            cache_system=True,
            role="expand",
        )
        result = ExpandedSearchQueries(**terms.model_dump())
    grounded = bool(toolkit.source_urls)
    if query_expansion_requires_grounding(settings) and not grounded:
        raise SourceUnavailableError(
            "tavily",
            "query-expansion agent produced no live grounding evidence",
        )
    grounding_queries = list(dict.fromkeys(toolkit.grounding_queries))
    source_urls = list(dict.fromkeys(toolkit.source_urls))
    if len(grounding_queries) > 20 or len(source_urls) > 100:
        logger.warning(
            "query_expansion_provenance_bounded",
            grounding_queries=len(grounding_queries),
            source_urls=len(source_urls),
        )
    result.provenance = QueryExpansionProvenance(
        origin="web_grounded_agent" if grounded else "model_without_live_grounding",
        grounded=grounded,
        model_name=settings.claude_triage_model,
        grounding_queries=grounding_queries[:20],
        source_urls=source_urls[:100],
    )
    return result


async def expand_without_search(
    client: ClaudeClient,
    system_prompt: str,
    compound_context: str,
    settings: Any,
) -> ExpandedSearchQueries:
    """Explicit ungrounded-screening path with constrained model decoding."""
    user_prompt = build_no_search_prompt(compound_context)

    terms, usage = await client.complete(
        system=system_prompt,
        user=user_prompt,
        response_model=ExpandedSearchQueryTerms,
        model=settings.claude_triage_model,
        max_tokens=2048,
        temperature=0.0,
        cache_system=True,
        role="expand",
    )
    result = ExpandedSearchQueries(**terms.model_dump())

    logger.debug(
        "expansion_no_search",
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )

    result.provenance = QueryExpansionProvenance(
        origin="model_without_live_grounding",
        grounded=False,
        model_name=settings.claude_triage_model,
    )
    return result


async def run_query_expansion(
    client: ClaudeClient,
    system_prompt: str,
    compound_context: str,
    tavily: TavilyClient,
    settings: Any,
) -> tuple[ExpandedSearchQueries, bool]:
    """Dispatch to the web-grounded or pure-LLM expansion path."""
    grounding_required = query_expansion_requires_grounding(settings)
    if grounding_required and not tavily.available:
        raise ConfigurationError(
            "Tavily API key not configured for required query-expansion grounding",
            source="tavily",
            step="query_expansion",
        )

    if tavily.available:
        result = await expand_with_search_agent(
            client,
            system_prompt,
            compound_context,
            tavily,
            settings,
        )
        return result, result.provenance.grounded

    return (
        await expand_without_search(
            client,
            system_prompt,
            compound_context,
            settings,
        ),
        False,
    )


def query_expansion_requires_grounding(settings: Any) -> bool:
    """Return whether query expansion is required to use live web grounding."""
    trust_mode = str(getattr(settings, "trust_mode", "") or "").strip().lower()
    return bool(
        getattr(settings, "required_record_components", [])
        or []
        or trust_mode == "counsel"
        or getattr(settings, "search_loop_enabled", False)
    )

"""Step 1.5: LLM Query Expansion — ResolvedCompound → ExpandedSearchQueries.

Uses a search agent pattern: Haiku gets a web_search tool (Tavily) and
autonomously decides what to search for — CPC codes, assignee names,
production methods — then generates structured output grounded in real data.

The explicitly ungrounded screening profile can use pure model knowledge.
When grounded expansion is required, Tavily grounding is mandatory and failures
propagate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog
from pydantic import ValidationError

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.clients.tavily import TavilyClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.pipeline.query_expansion_helpers import (
    build_compound_context,
    filter_invalid_cpc_codes,
)
from praviar_pipeline.pipeline.step1b_expand_helpers import (
    query_expansion_requires_grounding,
    run_query_expansion,
    validate_cpc_code,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound

logger = structlog.get_logger()


async def expand_search_queries(
    compound: ResolvedCompound,
) -> ExpandedSearchQueries:
    """Generate expanded search queries for a resolved compound.

    When Tavily is configured, uses a search agent pattern: the LLM gets
    a web_search tool and autonomously decides what to search for before
    generating structured output grounded in real search results.

    The explicitly ungrounded screening profile can use pure model knowledge
    with constrained decoding and records that provenance. When grounding is
    required, grounding failures propagate as configuration/source errors.

    Returns:
        ExpandedSearchQueries with LLM-generated search expansion terms. In
        screening mode, failures return empty expansion so search continues
        with compound-identity queries. In required-grounding mode,
        failures propagate so sparse search input cannot hide dependency gaps.
    """
    settings = get_settings()
    grounding_required = query_expansion_requires_grounding(settings)
    compound_context = build_compound_context(compound)
    failure_type: str | None = None

    try:
        async with ClaudeClient() as client:
            system_prompt = client.load_prompt("query_expansion_system.txt")

            # Check if Tavily is available for web-grounded search agent
            tavily = TavilyClient(required=query_expansion_requires_grounding(settings))
            try:
                result, web_grounded = await run_query_expansion(
                    client,
                    system_prompt,
                    compound_context,
                    tavily,
                    settings,
                )
            finally:
                await tavily.close()

        # Post-generation validation: strip invalid CPC codes
        valid_cpc, invalid = filter_invalid_cpc_codes(
            result,
            validate_cpc_code_fn=validate_cpc_code,
        )
        if invalid:
            logger.warning(
                "cpc_codes_filtered",
                valid=len(valid_cpc),
                invalid=len(invalid),
                invalid_codes=invalid,
            )

        logger.info(
            "query_expansion_complete",
            process_keywords=len(result.process_keywords),
            compound_class_terms=len(result.compound_class_terms),
            web_grounded=web_grounded,
        )

        return result

    except SourceUnavailableError as exc:
        failure_type = safe_exception_type(exc)
        logger.warning(
            "query_expansion_source_unavailable",
            error_type=failure_type,
            grounding_required=grounding_required,
        )
    except (httpx.HTTPError, ConnectionError, TimeoutError) as exc:
        failure_type = safe_exception_type(exc)
        logger.error(
            "query_expansion_failed",
            error_type=failure_type,
            grounding_required=grounding_required,
        )
    except (ValidationError, ValueError, KeyError) as exc:
        failure_type = safe_exception_type(exc)
        logger.error(
            "query_expansion_failed",
            error_type=failure_type,
            grounding_required=grounding_required,
        )

    if failure_type is not None and grounding_required:
        # Required grounding cannot silently degrade. Raise after leaving the
        # provider exception scope to avoid retaining credentials as context.
        raise SourceUnavailableError(
            "query_expansion",
            "grounded query expansion failed",
        ) from None

    return ExpandedSearchQueries()

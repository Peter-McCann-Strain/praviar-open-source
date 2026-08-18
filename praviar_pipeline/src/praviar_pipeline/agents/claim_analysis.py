"""ClaimAnalysisAgent — multi-turn adaptive escalation with specification lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.agents.base import ResearchAgent
from praviar_pipeline.agents.tools.patent_tools import PatentResearchToolkit
from praviar_pipeline.config import get_settings
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.utils.claim_parser import format_pre_parsed_claims, split_claims

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import Toolkit

logger = structlog.get_logger()


class ClaimAnalysisAgent(ResearchAgent):
    """Research agent for escalated patent claim analysis.

    Uses deterministic claim pre-parsing for consistent structure,
    then fetches patent specification text, constructs claim terms using
    Phillips v. AWH framework, and performs element-by-element analysis
    with self-critique.
    """

    @property
    def agent_type(self) -> str:
        return "claim_analysis"

    @property
    def model_id(self) -> str:
        return get_settings().claude_deep_model

    @property
    def max_rounds(self) -> int:
        return 5

    @property
    def prompt_file(self) -> str:
        return "claim_analysis_agent_system.txt"

    def build_toolkit(self, context: dict[str, Any]) -> Toolkit | None:
        """Build patent research toolkit with BigQuery spec retrieval."""
        patent_data = context.get("patent_data", {})
        return PatentResearchToolkit(patent_cache=patent_data)

    def format_task(self, task: str, context: dict[str, Any]) -> str:
        """Format the claim analysis task with patent and compound context.

        Uses deterministic claim pre-parsing to ensure consistent claim
        structure across runs — the LLM only judges, never parses.
        """
        compound_ctx = context.get("compound_context", "")
        patent_ctx = context.get("patent_context", "")
        claims_text = context.get("claims_text", "")
        bound_analysis_context = context.get("bound_analysis_context", "")

        parts = [
            "Perform element-by-element claim analysis for the following patent "
            "against the target compound.\n",
        ]
        if compound_ctx:
            parts.append(sanitize_untrusted_text(compound_ctx, data_type="compound_context"))
        if patent_ctx:
            parts.append(sanitize_untrusted_text(patent_ctx, data_type="patent_context"))
        if bound_analysis_context:
            parts.append(
                "--- BOUND ACCUSED-INSTRUMENTALITY CONTEXT ---\n"
                + sanitize_untrusted_text(
                    bound_analysis_context,
                    data_type="product_context",
                )
                + "\n--- END BOUND CONTEXT ---\n"
                "Assess every limitation against these exact facts. Missing product, "
                "use, process, actor, territory, or timing facts are UNCLEAR and must "
                "not be inferred from compound identity."
            )

        # Deterministic claim pre-parsing — same claims always produce same structure
        if claims_text:
            pre_parsed = split_claims(claims_text[:10000])
            if pre_parsed:
                formatted = format_pre_parsed_claims(pre_parsed)
                parts.append(sanitize_untrusted_text(formatted, data_type="pre_parsed_claims"))
                logger.debug(
                    "agent_claims_pre_parsed",
                    total_claims=len(pre_parsed),
                    independent=sum(1 for c in pre_parsed if c.claim_type == "independent"),
                )
            else:
                # Fallback: pass raw claims if parsing fails
                parts.append(
                    sanitize_untrusted_text(
                        claims_text,
                        max_len=10000,
                        data_type="claims_text",
                    )
                )

        parts.append(
            "\nInstructions:\n"
            "1. First, fetch the patent specification to understand claim term definitions\n"
            "2. For each ambiguous term, search for definitional language in the spec\n"
            "3. Use the pre-parsed claim structure above — do NOT re-parse, paraphrase, "
            "omit, or re-number; reproduce every element_text verbatim, including "
            "Element 0\n"
            "4. For each element, assess infringement with evidence-based reasoning\n"
            "5. Output your analysis as JSON matching the PatentAnalysis schema"
        )
        return "\n".join(parts)

"""CoverageAssessmentAgent — evaluates search coverage and identifies gaps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.agents.base import ResearchAgent
from praviar_pipeline.config import get_settings
from praviar_pipeline.sanitize import sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import Toolkit

logger = structlog.get_logger()


class CoverageAssessmentAgent(ResearchAgent):
    """Evaluates search coverage adequacy and identifies gaps.

    Assesses assignee distribution, CPC coverage, confidence distribution,
    search bias, and source failures to determine if additional search
    iterations are needed.
    """

    @property
    def agent_type(self) -> str:
        return "coverage_assessment"

    @property
    def model_id(self) -> str:
        return get_settings().claude_analysis_model  # Sonnet

    @property
    def max_rounds(self) -> int:
        return 2  # Quick assessment, not deep research

    @property
    def prompt_file(self) -> str:
        return "coverage_assessment_system.txt"

    def build_toolkit(self, context: dict[str, Any]) -> Toolkit | None:
        return None  # No tools needed — assessment is based on provided data

    def format_task(self, task: str, context: dict[str, Any]) -> str:
        compound_info = context.get("compound_info", "")
        search_stats = context.get("search_stats", "")
        triage_stats = context.get("triage_stats", "")
        source_health = context.get("source_health", "")
        queries_used = context.get("queries_used", "")
        iteration_number = context.get("iteration_number", 1)
        clearance_policy = context.get("clearance_policy", "")
        known_record_gaps = context.get("known_record_gaps", [])
        collection_directives = context.get("evidence_collection_directives", "  - none")
        matter_graph_summary = context.get("matter_graph_summary", "")
        known_record_gaps_text = "\n".join(f"  - {gap}" for gap in known_record_gaps) or "  - none"

        return (
            "Assess the supplied search-coverage evidence.\n\n"
            f"Iteration: {iteration_number}\n\n"
            + sanitize_untrusted_text(compound_info, data_type="compound_context")
            + "\n\n"
            + sanitize_untrusted_text(search_stats, data_type="search_statistics")
            + "\n\n"
            + sanitize_untrusted_text(triage_stats, data_type="triage_statistics")
            + "\n\n"
            + sanitize_untrusted_text(source_health, data_type="source_health")
            + "\n\n"
            + sanitize_untrusted_text(queries_used, data_type="queries_used")
            + "\n\n"
            + sanitize_untrusted_text(clearance_policy, data_type="clearance_policy")
            + "\n\n"
            + sanitize_untrusted_text(matter_graph_summary, data_type="matter_graph_summary")
            + "\n\n"
            + sanitize_untrusted_text(known_record_gaps_text, data_type="known_record_gaps")
            + "\n\n"
            + sanitize_untrusted_text(
                collection_directives,
                data_type="evidence_collection_directives",
            )
            + "\n\n"
            "Assess whether the search coverage is adequate for the stated clearance policy. "
            "If not, identify specific gaps and suggest NEW search terms or evidence-collection "
            "directions that were NOT in the original queries. High-priority unresolved evidence "
            "directives should keep coverage inadequate unless you can explain why they are "
            "non-decisive for the current matter."
        )

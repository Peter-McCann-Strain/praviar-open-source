"""CriticAgent — portfolio-level review of patent analyses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.agents.base import ResearchAgent
from praviar_pipeline.config import get_settings
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.tools import FTOToolkit

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import Toolkit

logger = structlog.get_logger()


class CriticAgent(ResearchAgent):
    """Reviews all patent analyses for consistency, completeness, and quality.

    Operates at the portfolio level, checking cross-patent consistency,
    risk-claim alignment, design-around feasibility, and confidence calibration.
    """

    @property
    def agent_type(self) -> str:
        return "critic"

    @property
    def model_id(self) -> str:
        return get_settings().claude_deep_model  # Opus for thorough review

    @property
    def max_rounds(self) -> int:
        return 3

    @property
    def prompt_file(self) -> str:
        return "critic_agent_system.txt"

    def build_toolkit(self, context: dict[str, Any]) -> Toolkit | None:
        patent_data = context.get("patent_data", {})
        if not patent_data:
            return None
        enabled = ["get_current_date", "lookup_patent"]
        return FTOToolkit(known_patents=patent_data, enabled_tools=enabled)

    def format_task(self, task: str, context: dict[str, Any]) -> str:
        portfolio_summary = context.get("portfolio_summary", "")
        compound_ctx = context.get("compound_context", "")

        return (
            f"{task}\n\n"
            + sanitize_untrusted_text(compound_ctx, data_type="compound_context")
            + "\n\n"
            + sanitize_untrusted_text(
                portfolio_summary,
                data_type="prior_model_portfolio_analyses",
            )
            + "\n\n"
            "Review all analyses for cross-patent consistency, risk-claim alignment, "
            "design-around feasibility, and confidence calibration. "
            "Identify specific issues with patent IDs and claim numbers."
        )

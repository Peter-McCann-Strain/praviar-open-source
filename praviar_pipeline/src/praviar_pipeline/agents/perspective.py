"""PerspectiveAgent — analyzes a patent from a specific expert perspective."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.agents.base import ResearchAgent
from praviar_pipeline.config import get_settings
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.tools import FTOToolkit

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient, Toolkit

logger = structlog.get_logger()


class PerspectiveAgent(ResearchAgent):
    """Research agent analyzing a patent from a specific expert perspective.

    Three perspectives available:
    - patent_attorney: Claim scope, literal infringement, prosecution history
    - medicinal_chemist: Structural similarity, design-around feasibility
    - business_analyst: Portfolio strength, litigation risk, licensing
    """

    def __init__(self, claude: ClaudeClient, perspective: str) -> None:
        super().__init__(claude)
        self._perspective = perspective

    @property
    def agent_type(self) -> str:
        return f"perspective_{self._perspective}"

    @property
    def model_id(self) -> str:
        return get_settings().claude_analysis_model  # Sonnet — not Opus

    @property
    def max_rounds(self) -> int:
        return 3

    @property
    def prompt_file(self) -> str:
        return f"perspective_{self._perspective}_system.txt"

    def build_toolkit(self, context: dict[str, Any]) -> Toolkit | None:
        patent_data = context.get("patent_data", {})
        if not patent_data:
            return None
        return FTOToolkit(
            known_patents=patent_data, enabled_tools=["get_current_date", "lookup_patent"]
        )

    def format_task(self, task: str, context: dict[str, Any]) -> str:
        compound_ctx = context.get("compound_context", "")
        patent_ctx = context.get("patent_context", "")
        base_analysis = context.get("base_analysis_summary", "")

        return (
            f"{task}\n\n"
            + sanitize_untrusted_text(compound_ctx, data_type="compound_context")
            + "\n\n"
            + sanitize_untrusted_text(patent_ctx, data_type="patent_context")
            + "\n\n"
            + sanitize_untrusted_text(base_analysis, data_type="prior_model_analysis")
            + "\n\n"
            "Provide your expert perspective analysis. Focus on findings specific "
            "to your area of expertise that the base analysis may have missed or "
            "insufficiently covered."
        )

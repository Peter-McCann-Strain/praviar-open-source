"""Deterministic Markdown renderer for FTO reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.rendering.design import risk_display as _risk_display  # noqa: F401
from praviar_pipeline.rendering.markdown_sections import (
    render_action_items,
    render_appendices,
    render_data_limitations,
    render_drawing_analysis,
    render_executive_summary,
    render_header,
    render_pipeline_summary,
    render_risk_matrix,
    render_single_patent,
    render_verification,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport


def render_markdown(report: FTOReport) -> str:
    """Render a complete Markdown FTO report."""
    lines: list[str] = []

    render_header(lines, report)
    render_executive_summary(lines, report)
    render_pipeline_summary(lines, report)
    render_risk_matrix(lines, report)
    render_action_items(lines, report)
    render_drawing_analysis(lines, report)

    lines.append("## Detailed Patent Analysis")
    lines.append("")
    for analysis in report.patent_analyses:
        render_single_patent(lines, analysis, report)
        lines.append("---")
        lines.append("")

    render_data_limitations(lines, report)
    render_verification(lines, report)
    render_appendices(lines, report)

    return "\n".join(lines)

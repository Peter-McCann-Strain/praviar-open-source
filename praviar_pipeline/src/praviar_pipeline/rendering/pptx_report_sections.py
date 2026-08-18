"""Slide builders for PPTX report rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.rendering.audience_projection import AudienceField
from praviar_pipeline.rendering.export_options import (
    ExportRenderOptions,
    default_export_options,
)
from praviar_pipeline.rendering.pptx_report_charts import (
    add_funnel_slide,
    add_risk_distribution_slide,
    add_risk_matrix_slide,
    add_timeline_slide,
)
from praviar_pipeline.rendering.pptx_report_closing import (
    add_appendix_slide,
    add_moderate_summary_slide,
    add_patent_deep_dive_slide,
    add_recommendations_slide,
)
from praviar_pipeline.rendering.pptx_report_intro import (
    add_compound_slide,
    add_cover_slide,
    add_disclaimer_slide,
    add_evidence_scope_slide,
    add_executive_summary_slide,
    add_methodology_slide,
)
from praviar_pipeline.rendering.pptx_report_shared import high_risk_analyses

__all__ = ["build_report_sections"]

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.branding import BrandingConfig


def build_report_sections(
    prs,
    report: FTOReport,
    branding: BrandingConfig,
    charts: dict[str, str],
    *,
    options: ExportRenderOptions | None = None,
) -> None:
    """Build the deck body for the requested export scope."""
    options = options or default_export_options()
    add_cover_slide(prs, report, branding)
    add_disclaimer_slide(prs, report, branding)
    add_evidence_scope_slide(prs, report, options=options)

    if options.includes("executive_summary"):
        add_executive_summary_slide(prs, report)

    if options.includes("patent_analysis"):
        add_compound_slide(prs, report)
        add_methodology_slide(prs, report)
        add_funnel_slide(prs, report, charts)
        add_risk_distribution_slide(prs, report, charts)
        add_risk_matrix_slide(prs, report)
        add_timeline_slide(prs, report, charts)

        if options.allows(AudienceField.PATENT_DETAIL):
            for analysis in high_risk_analyses(report)[:6]:
                add_patent_deep_dive_slide(prs, analysis, report)

            add_moderate_summary_slide(prs, report)

    if options.allows(AudienceField.RECOMMENDATIONS) and options.includes("executive_summary"):
        add_recommendations_slide(prs, report)

    if options.allows(AudienceField.PIPELINE_METADATA) and options.includes("pipeline_metadata"):
        add_appendix_slide(prs, report, branding)

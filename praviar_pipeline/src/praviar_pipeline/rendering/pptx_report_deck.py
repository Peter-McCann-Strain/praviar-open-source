"""Deck orchestration for PPTX report rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.rendering.pptx_report_sections import build_report_sections

if TYPE_CHECKING:
    from pptx.presentation import Presentation as PresentationType

    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.branding import BrandingConfig
    from praviar_pipeline.rendering.export_options import ExportRenderOptions


def generate_charts(report: FTOReport) -> dict[str, str]:
    """Generate all charts for the presentation. Returns dict of base64 PNGs."""
    charts: dict[str, str] = {}

    try:
        from praviar_pipeline.rendering.charts import (
            render_funnel_chart,
            render_patent_timeline,
            render_risk_distribution_chart,
        )

        if report.audit_trail.timing_data or report.audit_trail.total_patents_discovered > 0:
            charts["funnel"] = render_funnel_chart(report.audit_trail)

        if report.patent_analyses:
            charts["risk_distribution"] = render_risk_distribution_chart(report.patent_analyses)
            charts["timeline"] = render_patent_timeline(
                report.patent_analyses,
                report.patent_details,
            )
    except Exception:
        import structlog

        structlog.get_logger().warning("pptx_chart_generation_failed")

    return charts


def build_pptx_presentation(
    report: FTOReport,
    branding: BrandingConfig,
    *,
    options: ExportRenderOptions | None = None,
) -> PresentationType:
    """Build and return a python-pptx Presentation for an FTO report."""
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    charts = generate_charts(report)
    build_report_sections(prs, report, branding, charts, options=options)
    return prs

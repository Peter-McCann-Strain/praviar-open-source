"""DOCX section renderers for FTO reports.

This module preserves the public report section surface while delegating the
implementation to smaller helper modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.rendering.audience_projection import AudienceField
from praviar_pipeline.rendering.design import risk_display, risk_sort_key
from praviar_pipeline.rendering.docx_report_layout import add_styled_paragraph, get_risk_level
from praviar_pipeline.rendering.docx_report_sections_appendices import (
    add_appendices,
    add_disclaimer,
    add_recommendations,
    add_verification,
)
from praviar_pipeline.rendering.docx_report_sections_body import (
    add_claim_chart,
    add_doe_section,
    add_invalidity_section,
    add_patent_detail,
)
from praviar_pipeline.rendering.docx_report_sections_frontmatter import (
    add_compound_profile,
    add_cover_page,
    add_evidence_scope,
    add_executive_summary,
    add_methodology,
    add_risk_matrix,
)
from praviar_pipeline.rendering.export_options import (
    ExportRenderOptions,
    default_export_options,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.branding import BrandingConfig

__all__ = [
    "add_appendices",
    "add_claim_chart",
    "add_compound_profile",
    "add_cover_page",
    "add_disclaimer",
    "add_doe_section",
    "add_evidence_scope",
    "add_executive_summary",
    "add_invalidity_section",
    "add_methodology",
    "add_patent_detail",
    "add_recommendations",
    "add_risk_matrix",
    "add_verification",
    "build_report_sections",
]


def build_report_sections(
    doc,
    report: FTOReport,
    branding: BrandingConfig,
    *,
    options: ExportRenderOptions | None = None,
) -> None:
    """Build the document body for the requested export scope."""
    options = options or default_export_options()
    section_num = 0

    def next_section(title: str) -> str:
        nonlocal section_num
        section_num += 1
        return f"{section_num}. {title}"

    add_cover_page(doc, report, branding)
    add_evidence_scope(doc, report, next_section("Evidence Scope"))
    add_styled_paragraph(
        doc,
        f"Export audience: {options.audience_label}. "
        f"Included sections: {', '.join(options.section_labels)}.",
        size=9,
    )

    if options.includes("executive_summary"):
        add_executive_summary(doc, report, next_section("Executive Summary"))

    if options.includes("patent_analysis"):
        add_compound_profile(doc, report, next_section("Compound Profile"))
        add_methodology(doc, report, next_section("Search Methodology"))
        add_risk_matrix(
            doc,
            report,
            next_section("Risk Assessment Matrix"),
            options=options,
        )

    high_medium = [
        a
        for a in report.patent_analyses
        if a.risk_level in (get_risk_level("high"), get_risk_level("medium"))
    ]
    high_medium.sort(key=lambda a: risk_sort_key(a.risk_level))

    if (
        high_medium
        and options.allows(AudienceField.PATENT_DETAIL)
        and options.includes("patent_analysis", "claim_charts", "invalidity_assessment")
    ):
        doc.add_page_break()
        doc.add_heading(next_section("Detailed Patent Analysis"), level=1)
        for a in high_medium:
            add_patent_detail(doc, a, report, options=options)

    low_clear = [
        a
        for a in report.patent_analyses
        if a.risk_level not in (get_risk_level("high"), get_risk_level("medium"))
    ]
    if (
        low_clear
        and options.allows(AudienceField.PATENT_DETAIL)
        and options.includes("patent_analysis")
    ):
        doc.add_heading(next_section("Low-Risk Patents Summary"), level=1)
        for a in low_clear:
            add_styled_paragraph(
                doc,
                f"{a.patent_id} ({a.assignee}) — {risk_display(a.risk_level)}: "
                f"{a.risk_summary[:200]}",
                size=10,
            )

    if options.allows(AudienceField.RECOMMENDATIONS) and options.includes("executive_summary"):
        doc.add_page_break()
        add_recommendations(doc, report, next_section("Strategic Recommendations"))

    if options.allows(AudienceField.AUDIT_TRAIL) and options.includes("audit_trail"):
        doc.add_page_break()
        add_verification(doc, report, next_section("Verification & Quality"))

    if options.allows(AudienceField.PIPELINE_METADATA) and options.includes("pipeline_metadata"):
        add_appendices(doc, report)

    add_disclaimer(doc, report, branding)

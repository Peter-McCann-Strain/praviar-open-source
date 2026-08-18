"""End matter sections for DOCX report rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.output_safety import safe_processing_error_detail
from praviar_pipeline.rendering.design import (
    BRAND_PAPER,
    BRAND_SECONDARY_TEXT,
    RISK_BG,
    RISK_FILL,
    risk_display,
    risk_sort_key,
)
from praviar_pipeline.rendering.docx_report_layout import (
    add_styled_paragraph,
    get_risk_level,
    set_cell_shading,
    style_body_cell,
    style_header_cell,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.branding import BrandingConfig


def add_recommendations(doc, report: FTOReport, section_title: str) -> None:
    """Add strategic recommendations from action items."""
    doc.add_heading(section_title, level=1)

    if not report.action_items:
        doc.add_paragraph("No strategic recommendations generated for this analysis.")
        return

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_items = sorted(
        report.action_items,
        key=lambda item: priority_order.get(item.priority.value, 99),
    )

    for item in sorted_items:
        action_type = item.action_type.value.replace("_", " ").title()
        priority = item.priority.value.upper()
        add_styled_paragraph(
            doc,
            f"[{priority}] {action_type}: {item.description}",
            bold=True,
        )
        if item.patent_ids:
            add_styled_paragraph(doc, f"  Patents: {', '.join(item.patent_ids)}", size=10)
        if item.reasoning:
            add_styled_paragraph(doc, item.reasoning, size=10, color=BRAND_SECONDARY_TEXT)
        if item.estimated_timeline:
            add_styled_paragraph(
                doc,
                f"  Timeline: {item.estimated_timeline}",
                size=10,
                italic=True,
            )


def add_verification(doc, report: FTOReport, section_title: str) -> None:
    """Add verification and quality section."""
    doc.add_heading(section_title, level=1)

    passed = "Yes" if report.verification.all_passed else "No"
    add_styled_paragraph(doc, f"All checks passed: {passed}", bold=True)

    if report.verification.checks:
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        style_header_cell(table.rows[0].cells[0], "Check")
        style_header_cell(table.rows[0].cells[1], "Result")
        style_header_cell(table.rows[0].cells[2], "Details")

        for check in report.verification.checks:
            row = table.add_row()
            style_body_cell(row.cells[0], check.check_name)
            result = "PASS" if check.passed else "FAIL"
            style_body_cell(row.cells[1], result)
            set_cell_shading(
                row.cells[1],
                RISK_BG[get_risk_level("clear")]
                if check.passed
                else RISK_BG[get_risk_level("high")],
            )
            style_body_cell(row.cells[2], check.details[:200])

    if report.analysis_failures:
        doc.add_heading("Analysis Failures", level=2)
        for failure in report.analysis_failures:
            add_styled_paragraph(
                doc,
                f"{failure.patent_id} ({failure.step}): "
                f"{safe_processing_error_detail(failure.error_message)}",
                size=10,
                color=RISK_FILL[get_risk_level("high")],
            )

    if report.data_limitations:
        doc.add_heading("Data Limitations", level=2)
        for limitation in report.data_limitations:
            add_styled_paragraph(
                doc,
                f"[{limitation.category}] {limitation.description} — Impact: {limitation.impact}",
                size=10,
            )

    if report.llm_models_used:
        doc.add_heading("Model Attribution", level=2)
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        style_header_cell(table.rows[0].cells[0], "Role")
        style_header_cell(table.rows[0].cells[1], "Model")
        for role, model in report.llm_models_used.items():
            row = table.add_row()
            style_body_cell(row.cells[0], role)
            style_body_cell(row.cells[1], model)


def add_appendices(doc, report: FTOReport) -> None:
    """Add appendices with search parameters, patent list, and cost summary."""
    doc.add_heading("Appendices", level=1)

    if report.patent_analyses:
        doc.add_heading("A. Full Patent Listing", level=2)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        style_header_cell(table.rows[0].cells[0], "Patent")
        style_header_cell(table.rows[0].cells[1], "Assignee")
        style_header_cell(table.rows[0].cells[2], "Risk")
        style_header_cell(table.rows[0].cells[3], "Expiry")

        for analysis in sorted(
            report.patent_analyses,
            key=lambda item: risk_sort_key(item.risk_level),
        ):
            row = table.add_row()
            style_body_cell(row.cells[0], analysis.patent_id)
            style_body_cell(row.cells[1], analysis.assignee[:40])
            style_body_cell(row.cells[2], risk_display(analysis.risk_level))
            set_cell_shading(row.cells[2], RISK_BG.get(analysis.risk_level, BRAND_PAPER))
            style_body_cell(
                row.cells[3],
                analysis.expiry_date.isoformat() if analysis.expiry_date else "N/A",
            )

    doc.add_heading("B. Search Parameters", level=2)
    add_styled_paragraph(doc, f"Compound: {report.compound.name}", size=10)
    add_styled_paragraph(doc, f"SMILES: {report.compound.canonical_smiles}", size=10)
    add_styled_paragraph(doc, f"Sources: {', '.join(report.search_sources_used)}", size=10)
    add_styled_paragraph(doc, f"Execution profile: {report.execution_profile}", size=10)

    if report.estimated_cost_usd > 0:
        doc.add_heading("C. Cost Summary", level=2)
        add_styled_paragraph(
            doc,
            f"Total input tokens: {report.total_input_tokens:,}\n"
            f"Total output tokens: {report.total_output_tokens:,}\n"
            f"Estimated cost: ${report.estimated_cost_usd:.4f}",
            size=10,
        )


def add_disclaimer(doc, report: FTOReport, branding: BrandingConfig) -> None:
    """Add final disclaimer page."""
    doc.add_page_break()
    doc.add_heading("Disclaimer", level=1)

    add_styled_paragraph(
        doc,
        branding.effective_disclaimer_text,
        italic=True,
        size=9,
        color=BRAND_SECONDARY_TEXT,
    )

    add_styled_paragraph(
        doc,
        f"\n{branding.display_name} | Version: {report.praviar_pipeline_version} | "
        f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        size=8,
        color=BRAND_SECONDARY_TEXT,
    )

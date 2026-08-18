"""Patent detail sections for DOCX report rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.rendering.design import (
    BRAND_PAPER,
    BRAND_SECONDARY_TEXT,
    RISK_BG,
    RISK_FILL,
    risk_display,
)
from praviar_pipeline.rendering.docx_report_layout import (
    add_styled_paragraph,
    get_risk_level,
    set_cell_shading,
    status_bg,
    style_body_cell,
    style_header_cell,
)
from praviar_pipeline.rendering.docx_report_layout import (
    rgb_color as _rgb_color,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import ClaimAnalysis, PatentAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.report import FTOReport
    from praviar_pipeline.rendering.export_options import ExportRenderOptions


def add_patent_detail(
    doc,
    analysis: PatentAnalysis,
    report: FTOReport,
    *,
    options: ExportRenderOptions | None = None,
) -> None:
    """Add detailed analysis for one patent."""
    from praviar_pipeline.rendering.export_options import default_export_options

    options = options or default_export_options()
    risk = risk_display(analysis.risk_level)
    doc.add_heading(f"{analysis.patent_id} — {analysis.title[:80]}", level=2)

    p = doc.add_paragraph()
    run = p.add_run(f"Risk: {risk}")
    run.font.bold = True
    risk_color = RISK_FILL.get(analysis.risk_level, BRAND_SECONDARY_TEXT)
    run.font.color.rgb = _rgb_color(risk_color)

    add_styled_paragraph(
        doc,
        f"Assignee: {analysis.assignee}\n"
        f"Expiry: {analysis.expiry_date.isoformat() if analysis.expiry_date else 'Unknown'}\n"
        f"Claims analyzed: {len(analysis.claims_analyzed)}",
        size=10,
        color=BRAND_SECONDARY_TEXT,
    )

    if analysis.orange_book_info and analysis.orange_book_info.is_listed:
        ob = analysis.orange_book_info
        status = "LISTED — DELIST REQUESTED" if ob.delist_requested else "LISTED"
        add_styled_paragraph(
            doc,
            f"FDA Orange Book: {status}"
            + (f" | NDA: {', '.join(ob.nda_numbers)}" if ob.nda_numbers else "")
            + (f" | Products: {', '.join(ob.product_names[:3])}" if ob.product_names else ""),
            bold=True,
            size=10,
        )

    narrative = report.patent_narratives.get(analysis.patent_id, "")
    if narrative:
        doc.add_heading("Risk Assessment", level=3)
        add_styled_paragraph(doc, narrative)

    if options.includes("claim_charts"):
        for claim in analysis.claims_analyzed:
            add_claim_chart(doc, claim)

    doe_for_patent = [d for d in report.doe_assessments if d.patent_id == analysis.patent_id]
    if doe_for_patent:
        add_doe_section(doc, doe_for_patent)

    inv = next(
        (ia for ia in report.invalidity_assessments if ia.patent_id == analysis.patent_id),
        None,
    )
    if inv and options.includes("invalidity_assessment"):
        add_invalidity_section(doc, inv)

    if analysis.design_around_suggestions:
        doc.add_heading("Design-Around Suggestions", level=3)
        for i, suggestion in enumerate(analysis.design_around_suggestions, 1):
            add_styled_paragraph(
                doc,
                f"{i}. {suggestion.suggestion} (Element: {suggestion.element_avoided}, "
                f"Feasibility: {suggestion.feasibility})",
            )


def add_claim_chart(doc, claim: ClaimAnalysis) -> None:
    """Add a styled claim chart table."""
    doc.add_heading(
        f"Claim {claim.claim_number} ({claim.claim_type}) — "
        f"{claim.overall_status.value.upper().replace('_', ' ')}",
        level=3,
    )

    if not claim.elements:
        return

    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    style_header_cell(table.rows[0].cells[0], "#")
    style_header_cell(table.rows[0].cells[1], "Claim Element")
    style_header_cell(table.rows[0].cells[2], "Analysis")
    style_header_cell(table.rows[0].cells[3], "Status")

    for element in claim.elements:
        row = table.add_row()
        style_body_cell(row.cells[0], str(element.element_number))
        style_body_cell(row.cells[1], element.element_text)
        style_body_cell(row.cells[2], element.reasoning)

        status_text = element.status.value.upper().replace("_", " ")
        style_body_cell(row.cells[3], status_text)
        set_cell_shading(row.cells[3], status_bg(element.status.value))


def add_doe_section(doc, doe_assessments: list[DoEAssessment]) -> None:
    """Add Doctrine of Equivalents section."""
    doc.add_heading("Doctrine of Equivalents", level=3)

    for assessment in doe_assessments:
        equiv = {
            True: "EQUIVALENT",
            False: "NOT EQUIVALENT",
            None: "UNRESOLVED",
        }[assessment.overall_equivalent]
        add_styled_paragraph(
            doc,
            f"Claim {assessment.claim_number}, Element {assessment.element_number}: "
            f"{equiv} (Confidence: {assessment.confidence_band})",
            bold=True,
        )

        if assessment.estoppel.estoppel_applies:
            add_styled_paragraph(
                doc,
                f"  Prosecution History Estoppel APPLIES: {assessment.estoppel.surrendered_scope}",
                italic=True,
                color=RISK_FILL[get_risk_level("high")],
            )

        if assessment.fwr:

            def _fwr_label(value: bool | None) -> str:
                if value is None:
                    return "Unresolved"
                return "Same" if value else "Different"

            add_styled_paragraph(
                doc,
                f"  Function: {_fwr_label(assessment.fwr.same_function)} | "
                f"Way: {_fwr_label(assessment.fwr.same_way)} | "
                f"Result: {_fwr_label(assessment.fwr.same_result)}",
                size=10,
            )

        if assessment.reasoning:
            add_styled_paragraph(doc, assessment.reasoning, size=10, color=BRAND_SECONDARY_TEXT)


def add_invalidity_section(doc, inv: InvalidityAssessment) -> None:
    """Add invalidity assessment section."""
    doc.add_heading("Invalidity Screening", level=3)

    strength = inv.overall_invalidity_strength.upper() if inv.overall_invalidity_strength else "N/A"
    add_styled_paragraph(
        doc,
        f"Strength: {strength} | Confidence: {inv.confidence_band}",
        bold=True,
    )

    if inv.reasoning:
        add_styled_paragraph(doc, inv.reasoning, size=10)

    if inv.ptab and inv.ptab.has_been_challenged:
        add_styled_paragraph(
            doc,
            f"PTAB Proceedings: {len(inv.ptab.proceedings)}",
            bold=True,
        )
        for proceeding in inv.ptab.proceedings:
            add_styled_paragraph(
                doc,
                f"  {proceeding.proceeding_number} ({proceeding.type}) — "
                f"Status: {proceeding.status}"
                + (f", Decision: {proceeding.decision_date}" if proceeding.decision_date else ""),
                size=9,
            )

    if inv.enablement_screening:
        screening = inv.enablement_screening
        if screening.genus_claim_detected:
            add_styled_paragraph(
                doc,
                f"Enablement: Genus claim detected. "
                f"Specification enables full scope: {screening.specification_enables_full_scope}",
                bold=True,
            )
            if screening.amgen_v_sanofi_flags:
                add_styled_paragraph(
                    doc,
                    f"Amgen v. Sanofi flags: {', '.join(screening.amgen_v_sanofi_flags)}",
                    italic=True,
                    size=10,
                )

    if inv.prior_art:
        doc.add_heading("Prior Art References", level=4)
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        style_header_cell(table.rows[0].cells[0], "Reference")
        style_header_cell(table.rows[0].cells[1], "Title")
        style_header_cell(table.rows[0].cells[2], "Type")
        style_header_cell(table.rows[0].cells[3], "Anticipation")
        style_header_cell(table.rows[0].cells[4], "Obviousness")

        for reference in inv.prior_art[:10]:
            row = table.add_row()
            style_body_cell(row.cells[0], reference.reference_id)
            style_body_cell(row.cells[1], reference.title[:80])
            style_body_cell(row.cells[2], reference.reference_type)
            style_body_cell(row.cells[3], f"{reference.anticipation_score:.2f}")
            style_body_cell(row.cells[4], f"{reference.obviousness_score:.2f}")

    if inv.claim_charts:
        doc.add_heading("Invalidity Claim Charts", level=4)
        for chart in inv.claim_charts:
            add_styled_paragraph(
                doc,
                f"Claim {chart.claim_number} vs {chart.prior_art_reference_id}",
                bold=True,
                size=10,
            )

            table = doc.add_table(rows=1, cols=4)
            table.style = "Table Grid"
            style_header_cell(table.rows[0].cells[0], "Element")
            style_header_cell(table.rows[0].cells[1], "Claim Text")
            style_header_cell(table.rows[0].cells[2], "Prior Art")
            style_header_cell(table.rows[0].cells[3], "Disclosed")

            for entry in chart.entries:
                row = table.add_row()
                style_body_cell(row.cells[0], str(entry.element_number))
                style_body_cell(row.cells[1], entry.element_text)
                style_body_cell(row.cells[2], entry.prior_art_disclosure)
                style_body_cell(row.cells[3], entry.disclosed.upper())

                disc_bg = {
                    "yes": RISK_BG[get_risk_level("high")],
                    "partial": RISK_BG[get_risk_level("medium")],
                    "no": RISK_BG[get_risk_level("clear")],
                }.get(entry.disclosed.lower(), BRAND_PAPER)
                set_cell_shading(row.cells[3], disc_bg)

            if chart.chart_summary:
                add_styled_paragraph(doc, chart.chart_summary, italic=True, size=9)

    if inv.graham_factors:
        doc.add_heading("Graham Factors", level=4)
        gf = inv.graham_factors
        factors = [
            ("Scope & Content", gf.scope_and_content),
            ("Differences from Prior Art", gf.differences_from_prior_art),
            ("Level of Ordinary Skill", gf.level_of_ordinary_skill),
            ("Overall Obviousness", gf.overall_obviousness_assessment),
        ]
        for name, value in factors:
            if value:
                add_styled_paragraph(doc, f"{name}: {value[:300]}", size=10)

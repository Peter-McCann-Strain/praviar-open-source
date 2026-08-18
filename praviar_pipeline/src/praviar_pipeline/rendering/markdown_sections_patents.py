"""Patent section renderers for Markdown FTO reports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from praviar_pipeline.config import get_settings
from praviar_pipeline.rendering.design import risk_display as _risk_display
from praviar_pipeline.rendering.markdown_support import (
    collect_family_jurisdictions,
    format_assignment_entry,
    format_graham_factor_lines,
    format_patent_term_lines,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.drawing import PatentDrawingAnalysis
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.patent import OrangeBookInfo
    from praviar_pipeline.models.report import FTOReport


def _render_drawing_summary(lines: list[str], report: FTOReport) -> None:
    summary = report.drawing_summary
    if not summary:
        return
    lines.append(
        f"Analyzed {summary.get('patents_analyzed', 0)} patents, "
        f"extracted structures from {summary.get('patents_with_structures', 0)}. "
        f"{summary.get('total_structures', 0)} total structures identified, "
        f"{summary.get('patents_with_high_risk', 0)} patents with HIGH structural similarity."
    )
    lines.append("")


def _render_drawing_table(
    lines: list[str],
    patents_with_structures: list[PatentDrawingAnalysis],
) -> None:
    if not patents_with_structures:
        return
    lines.append("| Patent ID | Structures | Highest Tanimoto | Risk Signal |")
    lines.append("|-----------|-----------|-----------------|-------------|")
    for analysis in sorted(
        patents_with_structures,
        key=lambda item: item.highest_tanimoto,
        reverse=True,
    ):
        risk = analysis.highest_risk_signal.value.upper()
        lines.append(
            f"| {analysis.patent_id} | {analysis.structures_found} | "
            f"{analysis.highest_tanimoto:.3f} | {risk} |"
        )
    lines.append("")


def _render_high_similarity_structures(
    lines: list[str],
    patents_with_structures: list[PatentDrawingAnalysis],
) -> None:
    high_risk = [
        analysis
        for analysis in patents_with_structures
        if analysis.highest_risk_signal.value == "high"
    ]
    if not high_risk:
        return
    lines.append("### High-Similarity Structures")
    lines.append("")
    for analysis in high_risk:
        for structure in analysis.structures:
            if structure.tanimoto_to_target < 0.7:
                continue
            substructure_info = ""
            if structure.is_substructure_of_target:
                substructure_info = " (target is substructure)"
            elif structure.target_is_substructure:
                substructure_info = " (substructure of target)"
            lines.append(
                f"- **{analysis.patent_id}** Page {structure.page_number}: "
                f"`{structure.canonical_smiles}` — "
                f"Tanimoto {structure.tanimoto_to_target:.3f}{substructure_info} "
                f"(confidence: {structure.confidence:.2f})"
            )
    lines.append("")


def _render_low_confidence_note(
    lines: list[str],
    patents_with_structures: list[PatentDrawingAnalysis],
) -> None:
    low_confidence_count = sum(
        1
        for analysis in patents_with_structures
        for structure in analysis.structures
        if structure.confidence < 0.8
    )
    if low_confidence_count <= 0:
        return
    lines.append(
        f"> **Note:** {low_confidence_count} structures were extracted with "
        f"moderate confidence (<0.8). These should be verified by a chemist."
    )
    lines.append("")


def render_drawing_analysis(lines: list[str], report: FTOReport) -> None:
    """Render the drawing analysis section with Tanimoto table."""
    if not report.drawing_analyses:
        return

    lines.append("## Chemical Structure Analysis (Patent Drawings)")
    lines.append("")
    _render_drawing_summary(lines, report)
    patents_with_structures = [pa for pa in report.drawing_analyses if pa.structures_found > 0]
    _render_drawing_table(lines, patents_with_structures)
    _render_high_similarity_structures(lines, patents_with_structures)
    _render_low_confidence_note(lines, patents_with_structures)


def _render_patent_header(lines: list[str], analysis: PatentAnalysis) -> None:
    risk = _risk_display(analysis.risk_level)
    lines.append(f"### {analysis.patent_id}")
    lines.append("")
    lines.append(f"**Title:** {analysis.title}")
    lines.append(f"**Assignee:** {analysis.assignee}")
    lines.append(
        f"**Expiry:** {analysis.expiry_date.isoformat() if analysis.expiry_date else 'Unknown'}"
    )
    lines.append(f"**Risk Level:** {risk}")
    lines.append("")


def _render_patent_term(lines: list[str], detail: dict[str, Any]) -> None:
    term_info = detail.get("patent_term_info")
    if not term_info:
        return
    lines.append("#### Patent Term")
    lines.append("")
    lines.extend(format_patent_term_lines(term_info))
    lines.append("")


def _render_detail_orange_book(
    lines: list[str],
    orange_book: dict[str, Any] | None,
) -> bool:
    if not orange_book or not orange_book.get("is_listed"):
        return False
    status = "LISTED — DELIST REQUESTED" if orange_book.get("delist_requested") else "LISTED"
    lines.append(f"**FDA Orange Book:** {status}")
    if orange_book.get("nda_numbers"):
        lines.append(f"**NDA:** {', '.join(orange_book['nda_numbers'])}")
    if orange_book.get("active_ingredients"):
        lines.append(f"**Active Ingredient(s):** {', '.join(orange_book['active_ingredients'])}")
    if orange_book.get("product_names"):
        lines.append(f"**Product(s):** {', '.join(orange_book['product_names'][:5])}")
    if orange_book.get("drug_substance_patent"):
        lines.append("**Type:** Drug substance patent")
    if orange_book.get("drug_product_patent"):
        lines.append("**Type:** Drug product patent")
    lines.append("")
    return True


def _render_analysis_orange_book(
    lines: list[str],
    orange_book: OrangeBookInfo | None,
) -> None:
    if not orange_book or not orange_book.is_listed:
        return
    status = "LISTED — DELIST REQUESTED" if orange_book.delist_requested else "LISTED"
    lines.append(f"**FDA Orange Book:** {status}")
    if orange_book.nda_numbers:
        lines.append(f"**NDA:** {', '.join(orange_book.nda_numbers)}")
    if orange_book.active_ingredients:
        lines.append(f"**Active Ingredient(s):** {', '.join(orange_book.active_ingredients)}")
    if orange_book.product_names:
        lines.append(f"**Product(s):** {', '.join(orange_book.product_names[:5])}")
    lines.append("")


def _render_orange_book(
    lines: list[str],
    analysis: PatentAnalysis,
    detail: dict[str, Any],
) -> None:
    if _render_detail_orange_book(lines, detail.get("orange_book_info")):
        return
    _render_analysis_orange_book(lines, analysis.orange_book_info)


def _render_ptab_proceedings(lines: list[str], detail: dict[str, Any]) -> None:
    proceedings = detail.get("ptab_proceedings", [])
    if not proceedings:
        return
    lines.append("#### PTAB Proceedings")
    lines.append("")
    for proceeding in proceedings:
        proceeding_type = proceeding.get("proceeding_type", "Unknown")
        proceeding_number = proceeding.get("proceeding_number", "")
        status = proceeding.get("status", "Unknown")
        petitioner = proceeding.get("petitioner", "Unknown")
        lines.append(f"- **{proceeding_type} {proceeding_number}**: {status}")
        lines.append(f"  - Petitioner: {petitioner}")
        if proceeding.get("filing_date"):
            lines.append(f"  - Filed: {proceeding['filing_date']}")
        if proceeding.get("outcome"):
            lines.append(f"  - Outcome: {proceeding['outcome']}")
    lines.append("")


def _render_assignments(lines: list[str], detail: dict[str, Any]) -> None:
    assignments = detail.get("assignments", [])
    if not assignments:
        return
    lines.append("#### Ownership History")
    lines.append("")
    for assignment in assignments[:10]:
        lines.append(format_assignment_entry(assignment))
    lines.append("")


def _render_family(lines: list[str], detail: dict[str, Any]) -> None:
    family = detail.get("family")
    if not family or not family.get("members"):
        return
    jurisdictions = collect_family_jurisdictions(family)
    if not jurisdictions:
        return
    lines.append(
        f"**Patent Family:** {len(family['members'])} members across {', '.join(jurisdictions)}"
    )
    lines.append("")


def _render_detail_sections(
    lines: list[str],
    analysis: PatentAnalysis,
    detail: dict[str, Any],
) -> None:
    _render_patent_term(lines, detail)
    _render_orange_book(lines, analysis, detail)
    _render_ptab_proceedings(lines, detail)
    _render_assignments(lines, detail)
    _render_family(lines, detail)


def _render_patent_narrative(
    lines: list[str],
    analysis: PatentAnalysis,
    report: FTOReport,
) -> None:
    if analysis.patent_id not in report.patent_narratives:
        return
    lines.append(report.patent_narratives[analysis.patent_id])
    lines.append("")


def _render_claims(lines: list[str], analysis: PatentAnalysis) -> None:
    for claim in analysis.claims_analyzed:
        lines.append(f"**Claim {claim.claim_number}** ({claim.claim_type})")
        lines.append("")
        lines.append("| Element | Text | Status |")
        lines.append("|---------|------|--------|")
        for element in claim.elements:
            status = element.status.value.upper().replace("_", " ")
            text_short = element.element_text[:80] + (
                "..." if len(element.element_text) > 80 else ""
            )
            lines.append(f"| {element.element_number} | {text_short} | {status} |")
        lines.append("")


def _find_invalidity_assessment(
    analysis: PatentAnalysis,
    report: FTOReport,
) -> InvalidityAssessment | None:
    return next(
        (
            assessment
            for assessment in report.invalidity_assessments
            if assessment.patent_id == analysis.patent_id
        ),
        None,
    )


def _render_invalidity_claim_charts(
    lines: list[str],
    invalidity: InvalidityAssessment | None,
) -> None:
    if not invalidity or not invalidity.claim_charts:
        return
    lines.append("#### Invalidity Claim Charts")
    lines.append("")
    for chart in invalidity.claim_charts:
        lines.append(f"**Claim {chart.claim_number} vs {chart.prior_art_reference_id}**")
        lines.append("")
        lines.append("| Element | Element Text | Disclosed | Prior Art Disclosure |")
        lines.append("|---------|-------------|-----------|---------------------|")
        for entry in chart.entries:
            text_short = entry.element_text[:60] + ("..." if len(entry.element_text) > 60 else "")
            disclosure_short = entry.prior_art_disclosure[:60] + (
                "..." if len(entry.prior_art_disclosure) > 60 else ""
            )
            lines.append(
                f"| {entry.element_number} | {text_short} | "
                f"{entry.disclosed.upper()} | {disclosure_short} |"
            )
        lines.append("")
        if chart.chart_summary:
            lines.append(f"*{chart.chart_summary}*")
            lines.append("")


def _render_doe_assessments(
    lines: list[str],
    analysis: PatentAnalysis,
    report: FTOReport,
) -> None:
    assessments = [
        assessment
        for assessment in report.doe_assessments
        if assessment.patent_id == analysis.patent_id
    ]
    if not assessments:
        return
    lines.append("#### Doctrine of Equivalents")
    lines.append("")
    for assessment in assessments:
        equivalent = {
            True: "Equivalent",
            False: "Not equivalent",
            None: "Unresolved",
        }[assessment.overall_equivalent]
        lines.append(
            f"- Claim {assessment.claim_number}, Element {assessment.element_number}: "
            f"**{equivalent}** ({assessment.confidence_band})"
        )
        if assessment.estoppel.estoppel_applies:
            lines.append(f"  - Estoppel applies: {assessment.estoppel.surrendered_scope}")
    lines.append("")


def _render_invalidity_screening(
    lines: list[str],
    invalidity: InvalidityAssessment | None,
) -> None:
    if not invalidity:
        return
    lines.append("#### Invalidity Screening")
    lines.append("")
    lines.append(f"**Strength:** {invalidity.overall_invalidity_strength}")
    lines.append(f"**Evidence Level:** {invalidity.confidence_band}")
    lines.append("")
    if invalidity.prior_art:
        lines.append(f"Prior art references: {len(invalidity.prior_art)}")
    if invalidity.ptab.has_been_challenged:
        lines.append(f"PTAB proceedings: {len(invalidity.ptab.proceedings)}")
        if invalidity.ptab.all_claims_cancelled:
            lines.append(f"Claims cancelled: {invalidity.ptab.all_claims_cancelled}")
    if invalidity.graham_factors:
        lines.append("")
        lines.append("**Graham Factors:**")
        max_characters = get_settings().render_graham_max_chars
        lines.extend(format_graham_factor_lines(invalidity.graham_factors, max_characters))
    lines.append("")


def render_single_patent(lines: list[str], a: PatentAnalysis, report: FTOReport) -> None:
    """Render the full analysis block for one patent."""
    _render_patent_header(lines, a)
    detail = report.patent_details.get(a.patent_id, {})
    _render_detail_sections(lines, a, detail)
    _render_patent_narrative(lines, a, report)
    _render_claims(lines, a)
    invalidity = _find_invalidity_assessment(a, report)
    _render_invalidity_claim_charts(lines, invalidity)
    _render_doe_assessments(lines, a, report)
    _render_invalidity_screening(lines, invalidity)

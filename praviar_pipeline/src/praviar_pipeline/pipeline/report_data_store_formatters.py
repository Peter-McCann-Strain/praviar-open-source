"""Text formatters for :mod:`praviar_pipeline.pipeline.report_data_store`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.drawing import PatentDrawingAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment


def format_analysis_text(analysis: PatentAnalysis | None, patent_id: str) -> str:
    """Format a PatentAnalysis as human-readable text for tool output."""
    if analysis is None:
        return f"No analysis found for {patent_id}."

    lines = [
        f"Patent: {analysis.patent_id}",
        f"Title: {analysis.title}",
        f"Assignee: {analysis.assignee}",
        f"Risk Level: {analysis.risk_level.value.upper()}",
        f"Expiry: {analysis.expiry_date or 'unknown'}",
        f"Risk Summary: {analysis.risk_summary}",
        "",
    ]

    if analysis.claims_analyzed:
        lines.append(f"Claims Analyzed: {len(analysis.claims_analyzed)}")
        for claim in analysis.claims_analyzed:
            met = sum(1 for element in claim.elements if element.status.value == "met")
            total = len(claim.elements)
            lines.append(
                f"\n  Claim {claim.claim_number} "
                f"(type: {claim.claim_type}): "
                f"{met}/{total} elements met"
            )
            for element in claim.elements:
                lines.append(
                    f"    Element {element.element_number}: {element.status.value.upper()}"
                    f" — {element.element_text[:200]}"
                )
                if element.reasoning:
                    lines.append(f"      Reasoning: {element.reasoning[:300]}")

    if analysis.design_around_suggestions:
        lines.append(f"\nDesign-Around Suggestions: {len(analysis.design_around_suggestions)}")
        for suggestion in analysis.design_around_suggestions:
            lines.append(f"  - {suggestion.suggestion[:300]}")

    return "\n".join(lines)[:8000]


def format_doe_text(doe_list: list[DoEAssessment], patent_id: str) -> str:
    """Format DoE assessments for a patent."""
    if not doe_list:
        return f"No Doctrine of Equivalents assessment for {patent_id}."

    lines = [f"DoE Assessment for {patent_id}:"]
    for assessment in doe_list:
        lines.append(f"\n  Claim {assessment.claim_number}:")
        lines.append(f"    Overall Equivalent: {assessment.overall_equivalent}")
        lines.append(f"    Confidence: {assessment.confidence_band}")
        if assessment.fwr is not None:
            fwr = assessment.fwr
            lines.append(
                f"    FWR: function={fwr.same_function}, "
                f"way={fwr.same_way}, result={fwr.same_result}"
            )
        if hasattr(assessment, "estoppel") and assessment.estoppel:
            estoppel = assessment.estoppel
            if hasattr(estoppel, "estoppel_applies"):
                lines.append(f"    Estoppel Applies: {estoppel.estoppel_applies}")
            if hasattr(estoppel, "surrendered_scope") and estoppel.surrendered_scope:
                lines.append(f"    Surrendered Scope: {estoppel.surrendered_scope[:200]}")
    return "\n".join(lines)[:8000]


def format_invalidity_text(
    invalidity: InvalidityAssessment | None,
    patent_id: str,
) -> str:
    """Format InvalidityAssessment for a patent."""
    if invalidity is None:
        return f"No invalidity assessment for {patent_id}."

    lines = [
        f"Invalidity Assessment for {patent_id}:",
        f"Overall Strength: {invalidity.overall_invalidity_strength}",
        f"Confidence: {invalidity.confidence_band}",
        f"Reasoning: {invalidity.reasoning[:500]}",
    ]

    if hasattr(invalidity, "prior_art") and invalidity.prior_art:
        lines.append(f"\nPrior Art References ({len(invalidity.prior_art)}):")
        for reference in invalidity.prior_art:
            ref_line = f"  - {reference.title[:200]}"
            if hasattr(reference, "publication_date") and reference.publication_date:
                ref_line += f" ({reference.publication_date})"
            if hasattr(reference, "doi") and reference.doi:
                ref_line += f" DOI: {reference.doi}"
            if hasattr(reference, "reference_id") and reference.reference_id:
                ref_line += f" [ID: {reference.reference_id}]"
            if hasattr(reference, "reference_type") and reference.reference_type:
                ref_line += f" [{reference.reference_type}]"
            lines.append(ref_line)

    if hasattr(invalidity, "ptab") and invalidity.ptab:
        ptab = invalidity.ptab
        if ptab.has_been_challenged:
            lines.append("\nPTAB Proceedings:")
            for proceeding in ptab.proceedings:
                proceeding_line = (
                    f"  - {proceeding.type} {proceeding.proceeding_number}: {proceeding.status}"
                )
                if proceeding.outcome_summary:
                    proceeding_line += f" ({proceeding.outcome_summary[:200]})"
                lines.append(proceeding_line)

    return "\n".join(lines)[:8000]


def format_patent_details_text(detail: dict | None, patent_id: str) -> str:
    """Format enrichment data for a patent (PTAB, OB, term, assignments)."""
    if detail is None:
        return f"No enrichment data for {patent_id}."

    lines = [f"Patent Details for {patent_id}:"]

    ptab_procs = detail.get("ptab_proceedings", [])
    if ptab_procs:
        lines.append("\nPTAB Proceedings:")
        for ptab_proc in ptab_procs[:10]:
            lines.append(
                f"  - {ptab_proc.get('proceeding_type', 'Unknown')} "
                f"{ptab_proc.get('proceeding_number', '')}: "
                f"{ptab_proc.get('status', 'unknown')} "
                f"(petitioner: {ptab_proc.get('petitioner', 'unknown')})"
            )

    orange_book = detail.get("orange_book_info")
    if orange_book and orange_book.get("is_listed"):
        products = ", ".join(orange_book.get("product_names", [])[:5])
        lines.append(
            f"\nOrange Book: Listed"
            f" (NDA: {', '.join(orange_book.get('nda_numbers', [])[:3])},"
            f" products: {products})"
        )

    patent_term = detail.get("patent_term_info")
    if patent_term:
        td_note = ""
        if patent_term.get("terminal_disclaimer"):
            linked = patent_term.get("td_linked_patent", "unknown")
            td_note = f", terminal disclaimer (linked to {linked})"
        lines.append(
            f"\nPatent Term: expires {patent_term.get('adjusted_expiry', 'unknown')}"
            f", PTA {patent_term.get('pta_days', 0)} days"
            f", maintenance {patent_term.get('maintenance_fee_status', 'unknown')}"
            f"{td_note}"
        )

    assignments = detail.get("assignments", [])
    if assignments:
        lines.append("\nOwnership History:")
        for assignment in assignments[:5]:
            lines.append(
                f"  - {assignment.get('conveyance', 'Transfer')}"
                f" ({assignment.get('recorded_date', 'unknown')})"
                f" from {assignment.get('assignor', 'unknown')}"
                f" to {assignment.get('assignee', 'unknown')}"
            )

    events = detail.get("legal_events", [])
    if events:
        lines.append(f"\nLegal Events ({len(events)} total):")
        for event in events[:5]:
            lines.append(f"  - {event.get('date', '')}: {event.get('description', '')[:200]}")

    return "\n".join(lines)[:8000]


def format_drawing_evidence_text(
    drawing: PatentDrawingAnalysis | None,
    patent_id: str,
) -> str:
    """Format drawing/OCSR analysis for a patent."""
    if drawing is None:
        return f"No drawing analysis for {patent_id}."

    lines = [
        f"Drawing Analysis for {patent_id}:",
        f"Structures Found: {drawing.structures_found or 0}",
    ]

    if hasattr(drawing, "highest_tanimoto") and drawing.highest_tanimoto is not None:
        lines.append(f"Highest Tanimoto Similarity: {drawing.highest_tanimoto:.3f}")

    if hasattr(drawing, "structures") and drawing.structures:
        for index, structure in enumerate(drawing.structures[:5], 1):
            structure_line = f"  Structure {index}:"
            if hasattr(structure, "tanimoto_to_target"):
                structure_line += f" Tanimoto={structure.tanimoto_to_target:.3f}"
            if hasattr(structure, "is_substructure_of_target"):
                structure_line += f" Substructure={structure.is_substructure_of_target}"
            lines.append(structure_line)

    return "\n".join(lines)[:4000]


def format_prior_art_references_text(
    invalidity: InvalidityAssessment | None,
    patent_id: str,
) -> str:
    """Format prior art references for bibliography building."""
    if invalidity is None or not hasattr(invalidity, "prior_art") or not invalidity.prior_art:
        return f"No prior art references for {patent_id}."

    lines = [f"Prior Art References for {patent_id} ({len(invalidity.prior_art)} total):"]
    for reference in invalidity.prior_art:
        entry = [f"  Title: {reference.title[:300]}"]
        if hasattr(reference, "reference_id") and reference.reference_id:
            entry.append(f"  ID: {reference.reference_id}")
        if hasattr(reference, "reference_type") and reference.reference_type:
            entry.append(f"  Type: {reference.reference_type}")
        if hasattr(reference, "publication_date") and reference.publication_date:
            entry.append(f"  Published: {reference.publication_date}")
        if hasattr(reference, "doi") and reference.doi:
            entry.append(f"  DOI: {reference.doi}")
        if hasattr(reference, "url") and reference.url:
            entry.append(f"  URL: {reference.url}")
        if hasattr(reference, "anticipation_score") and reference.anticipation_score is not None:
            entry.append(f"  Anticipation Score: {reference.anticipation_score:.2f}")
        if hasattr(reference, "obviousness_score") and reference.obviousness_score is not None:
            entry.append(f"  Obviousness Score: {reference.obviousness_score:.2f}")
        lines.append("\n".join(entry))
        lines.append("")

    return "\n".join(lines)[:8000]

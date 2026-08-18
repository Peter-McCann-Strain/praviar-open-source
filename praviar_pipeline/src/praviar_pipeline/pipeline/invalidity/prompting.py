"""Prompt-building helpers for invalidity analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.config import get_settings
from praviar_pipeline.sanitize import sanitize_prompt_value, sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.invalidity import PriorArtReference, PTABResult


def build_invalidity_prompt(
    *,
    analysis: PatentAnalysis,
    compound: ResolvedCompound,
    ptab: PTABResult,
    prior_art: list[PriorArtReference] | None = None,
    examiner_citations: dict[str, list[str]] | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
) -> str:
    """Build the user prompt for invalidity assessment."""
    settings = get_settings()

    ptab_context = ""
    if ptab.has_been_challenged:
        ptab_context = f"\nPTAB History: {len(ptab.proceedings)} proceedings. "
        if ptab.all_claims_cancelled:
            ptab_context += f"Claims cancelled: {ptab.all_claims_cancelled}"

    citation_context = ""
    if examiner_citations:
        examiner_refs = examiner_citations.get("examiner", [])
        applicant_refs = examiner_citations.get("applicant", [])
        if examiner_refs or applicant_refs:
            citation_context = "\n\nProsecution Citation History:"
            if examiner_refs:
                refs = ", ".join(examiner_refs[: settings.invalidity_examiner_refs_display])
                citation_context += f"\n- Examiner-cited references ({len(examiner_refs)}): {refs}"
            if applicant_refs:
                refs = ", ".join(applicant_refs[: settings.invalidity_applicant_refs_display])
                citation_context += (
                    f"\n- Applicant-cited references ({len(applicant_refs)}): {refs}"
                )

    prior_art_context = ""
    if prior_art:
        prior_art_context = f"\n\nScholarly Prior Art Found ({len(prior_art)} references):"
        for ref in prior_art[: settings.invalidity_prior_art_context_max]:
            date_str = ref.publication_date.isoformat() if ref.publication_date else "unknown date"
            authors = (
                ", ".join(ref.authors[: settings.invalidity_authors_max])
                if ref.authors
                else "unknown authors"
            )
            prior_art_context += f"\n- {ref.title} ({authors}, {date_str})"
            if ref.doi:
                prior_art_context += f" [DOI: {ref.doi}]"

    claim_elements_context = ""
    if analysis.claims_analyzed:
        claim_elements_context = "\n\nClaim Elements for Chart Construction:"
        for claim in analysis.claims_analyzed:
            claim_elements_context += f"\nClaim {claim.claim_number} ({claim.claim_type}):"
            for elem in claim.elements:
                status = elem.status.value if hasattr(elem.status, "value") else str(elem.status)
                claim_elements_context += (
                    f'\n  Element {elem.element_number}: "{elem.element_text}" [{status}]'
                )

    user_prompt = (
        "Assess potential invalidity arguments for the "
        "following blocking patent.\n\n"
        f"Target Compound: {sanitize_prompt_value(compound.name)} "
        f"({sanitize_prompt_value(compound.canonical_smiles, max_len=2000)})\n\n"
        f"Patent: {sanitize_prompt_value(analysis.patent_id)}\n"
        + sanitize_untrusted_text(
            "\n".join(
                (
                    f"Title: {analysis.title}",
                    f"Assignee: {analysis.assignee}",
                    f"Risk Level: {analysis.risk_level.value}",
                    f"Risk Summary: {analysis.risk_summary}",
                    ptab_context,
                    citation_context,
                    prior_art_context,
                    claim_elements_context,
                )
            ),
            data_type="invalidity_evidence",
        )
        + "\n\n"
    )

    if drawing_evidence and drawing_evidence.has_structures(analysis.patent_id):
        drawing_text = drawing_evidence.summary_for_prompt(
            analysis.patent_id, max_structures=5, min_tanimoto=0.2
        )
        if drawing_text:
            user_prompt += (
                sanitize_untrusted_text(
                    drawing_text,
                    data_type="drawing_evidence_summary",
                )
                + "\n\n"
                "The structures above were extracted from the patent's own drawings. "
                "These may serve as disclosure evidence (§102) or as starting points "
                "for obviousness analysis (§103) when combined with other prior art.\n\n"
            )

    user_prompt += (
        "Instructions:\n"
        "1. Identify potential invalidity arguments under "
        "§102 (anticipation), §103 (obviousness), "
        "and §112 (written description/enablement).\n"
        "2. For EACH prior art reference, construct a CLAIM "
        "CHART mapping every claim element to specific "
        "disclosure with citations.\n"
        "3. Apply the Graham v. John Deere four-factor "
        "analysis for any obviousness arguments.\n"
        "4. Screen for enablement/written description issues, "
        "especially for genus claims (Amgen v. Sanofi).\n"
        "5. Where examiner citations or scholarly prior art "
        "are provided, reference specific works.\n\n"
        "Note: This is a preliminary screening assessment. "
        "All arguments should be verified by a patent attorney."
    )

    return user_prompt

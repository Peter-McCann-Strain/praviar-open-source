"""Shared formatting utilities for LLM prompts across pipeline steps."""

from __future__ import annotations

from typing import TYPE_CHECKING

from praviar_pipeline.sanitize import sanitize_prompt_value

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.triage import TriageResult


def _truncate_at_word_boundary(text: str, max_chars: int) -> str:
    """Truncate text at a word boundary, appending ellipsis marker."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Find last space to avoid cutting mid-word
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]
    return truncated + "\u2026"


def format_compound_context(
    compound: ResolvedCompound,
    *,
    include_inchi: bool = False,
    include_weight: bool = False,
    max_synonyms: int = 10,
) -> str:
    """Standard compound formatting for LLM prompts.

    Used by triage (step 3) and adaptive claim analysis (step 4).
    """
    # ``name`` falls back to raw user input when PubChem returns a CID without
    # an IUPACName, and synonyms/CAS/functional-group labels are untrusted
    # external PubChem text. Scrub every free-text, externally-derived field
    # before it is interpolated into the triage/analysis prompt so an injected
    # "ignore previous instructions" / forged "system:" turn cannot coerce the
    # model. SMILES/formula/InChIKey are structural and pattern-constrained.
    parts = [
        f"Target Compound: {sanitize_prompt_value(compound.name)}",
        f"SMILES: {compound.canonical_smiles}",
        f"Molecular Formula: {compound.molecular_formula}",
    ]
    if compound.inchi_key:
        parts.append(f"InChIKey: {compound.inchi_key}")
    if include_inchi and compound.inchi:
        parts.append(f"InChI: {compound.inchi}")
    if include_weight and compound.molecular_weight:
        parts.append(f"Molecular Weight: {compound.molecular_weight}")
    if compound.cas_numbers:
        parts.append(
            f"CAS Numbers: {', '.join(sanitize_prompt_value(c) for c in compound.cas_numbers[:5])}"
        )
    if compound.functional_groups:
        parts.append(
            "Functional Groups: "
            f"{', '.join(sanitize_prompt_value(g) for g in compound.functional_groups)}"
        )
    if compound.synonyms:
        parts.append(
            "Key Synonyms: "
            f"{', '.join(sanitize_prompt_value(s) for s in compound.synonyms[:max_synonyms])}"
        )
    return "\n".join(parts)


def format_patent_context(
    patent: PatentHit,
    *,
    triage: TriageResult | None = None,
    max_abstract: int = 0,
    max_claims: int = 0,
    include_dates: bool = False,
) -> str:
    """Standard patent formatting for LLM prompts.

    Args:
        patent: The patent hit to format.
        triage: Optional triage result for key claims context.
        max_abstract: Truncate abstract to N chars (0 = full text).
        max_claims: Truncate claims to N chars (0 = full text).
        include_dates: Include filing_date, expiry_date, legal_status when set.
    """
    parts = [f"Patent ID: {patent.patent_id}"]
    if patent.title:
        parts.append(f"Title: {patent.title}")
    if patent.assignees:
        parts.append(f"Assignee: {', '.join(patent.assignees[:3])}")
    if include_dates:
        if patent.filing_date:
            parts.append(f"Filing Date: {patent.filing_date.isoformat()}")
        if patent.expiry_date:
            parts.append(f"Expiry Date: {patent.expiry_date.isoformat()}")
        if patent.legal_status:
            parts.append(f"Legal Status: {patent.legal_status.value}")
    if patent.abstract:
        abstract = patent.abstract
        if max_abstract:
            abstract = _truncate_at_word_boundary(abstract, max_abstract)
        parts.append(f"\nAbstract: {abstract}")
    if patent.claims_text:
        claims = patent.claims_text
        if max_claims:
            claims = _truncate_at_word_boundary(claims, max_claims)
            label = f"Claims (first {max_claims} chars)"
        else:
            label = "FULL CLAIM TEXT"
        parts.append(f"\n{label}:\n{claims}")
    elif not patent.claims_text and patent.abstract:
        parts.append("\nNOTE: Full claim text not available. Analysis based on abstract only.")
    if triage and triage.key_claims:
        parts.append(f"\nPriority claims identified in triage: {triage.key_claims}")
    return "\n".join(parts)


def format_drawing_evidence(
    drawing_evidence: DrawingEvidenceStore,
    patent_id: str,
    *,
    detail_level: str = "standard",
    max_structures: int = 10,
    min_tanimoto: float = 0.3,
) -> str:
    """Format drawing evidence for injection into LLM prompts.

    Args:
        drawing_evidence: The evidence store from step 2.75.
        patent_id: Which patent to format for.
        detail_level: "brief" (triage), "standard" (analysis), "detailed" (invalidity).
        max_structures: Max structures to include in output.
        min_tanimoto: Only include structures above this threshold.
    """
    if drawing_evidence is None:
        return ""

    if detail_level == "brief":
        return drawing_evidence.brief_summary(patent_id)

    return drawing_evidence.summary_for_prompt(
        patent_id,
        max_structures=max_structures,
        min_tanimoto=min_tanimoto,
    )

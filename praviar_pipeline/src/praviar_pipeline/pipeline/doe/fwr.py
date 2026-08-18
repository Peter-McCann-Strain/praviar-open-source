"""Function-way-result helpers for doctrine of equivalents analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from praviar_pipeline.config import Settings, get_settings
from praviar_pipeline.models.equivalents import DoEAssessment, EstoppelResult, FWRAssessment
from praviar_pipeline.sanitize import sanitize_prompt_value, sanitize_untrusted_text

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.pipeline.doe.candidates import DoECandidate


# Maximum characters of prosecution context injected into the FWR prompt.
# PAIR file wrappers can be hundreds of MB — we already consume a parsed
# profile from Step 4 enrichment, but cap it to keep the prompt bounded.
_PROSECUTION_CONTEXT_CAP = 4000

ConfidenceBand = Literal["HIGH", "MODERATE", "LOW"]


def build_prosecution_context_summary(context: dict[str, Any] | None) -> str:
    """Render a compact, Festo-relevant text summary from a cached prosecution context.

    `context` is a single patent's entry from the Step 4 `prosecution_cache` (US only).
    Returns "" when the context is empty or contains no relevant signals.
    """
    if not context:
        return ""

    lines: list[str] = []

    office_action_count = int(context.get("office_action_count", 0) or 0)
    amendment_count = int(context.get("amendment_entry_count", 0) or 0)
    rejection_bases = list(context.get("rejection_bases", []) or [])
    estoppel_flags = list(context.get("estoppel_risk_flags", []) or [])
    narrowing_claims = list(context.get("narrowing_claim_numbers", []) or [])
    rejected_claims = list(context.get("rejected_claim_numbers", []) or [])
    amendments_summary = str(context.get("amendments", "") or "").strip()
    office_actions_summary = str(context.get("office_actions", "") or "").strip()

    if office_action_count or rejection_bases:
        bases = ", ".join(str(b) for b in rejection_bases[:6]) if rejection_bases else "unspecified"
        lines.append(f"- Office actions: {office_action_count}; rejection bases: {bases}")
    if amendment_count:
        lines.append(
            f"- Amendment/response events: {amendment_count}"
            + (
                f"; narrowed claims: {', '.join(str(c) for c in narrowing_claims[:8])}"
                if narrowing_claims
                else ""
            )
        )
    if rejected_claims:
        lines.append(f"- Rejected claims: {', '.join(str(c) for c in rejected_claims[:8])}")
    if estoppel_flags:
        lines.append("- Estoppel risk flags: " + ", ".join(estoppel_flags[:8]))
    if amendments_summary:
        lines.append("- Amendments excerpt:\n" + amendments_summary)
    if office_actions_summary:
        lines.append("- Office actions excerpt:\n" + office_actions_summary)

    if not lines:
        return ""

    rendered = "\n".join(lines)
    if len(rendered) > _PROSECUTION_CONTEXT_CAP:
        rendered = rendered[:_PROSECUTION_CONTEXT_CAP] + "\n... [truncated]"
    return rendered


def build_fwr_user_prompt(
    candidate: DoECandidate,
    compound: ResolvedCompound,
    drawing_evidence: DrawingEvidenceStore | None = None,
    prosecution_context: str | None = None,
) -> str:
    """Build the user prompt for a single FWR assessment."""
    user_prompt = (
        "Assess whether the Doctrine of Equivalents applies to the "
        "following claim element.\n\n"
        f"Target Compound: {sanitize_prompt_value(compound.name)}\n"
        f"SMILES: {sanitize_prompt_value(compound.canonical_smiles, max_len=2000)}\n"
        f"Molecular Formula: {sanitize_prompt_value(compound.molecular_formula)}\n\n"
        f"Patent: {sanitize_prompt_value(candidate['patent_id'])}\n"
        f"Claim {candidate['claim_number']}, "
        f"Element {candidate['element_number']}:\n"
        + sanitize_untrusted_text(candidate["element_text"], data_type="claim_element")
        + "\n\n"
        "Prior analysis determined this element is NOT MET literally "
        "because:\n"
        + sanitize_untrusted_text(candidate["element_reasoning"], data_type="prior_model_reasoning")
        + "\n\n"
        "Apply the Function-Way-Result test to determine if the target "
        "compound/process is equivalent under the Doctrine of Equivalents."
    )

    if drawing_evidence and drawing_evidence.has_structures(candidate["patent_id"]):
        structures = drawing_evidence.get_structures(candidate["patent_id"], min_tanimoto=0.2)
        if structures:
            best = max(structures, key=lambda structure: structure.tanimoto_to_target)
            user_prompt += (
                "\n\nSTRUCTURAL SIMILARITY EVIDENCE (from patent drawings):\n"
                "The patent drawings contain a structure (SMILES: "
                f"{sanitize_prompt_value(best.canonical_smiles, max_len=2000)}) "
                f"with Tanimoto similarity {best.tanimoto_to_target:.3f} to the target compound. "
            )
            if best.is_substructure_of_target or best.target_is_substructure:
                user_prompt += "A substructure relationship exists between the compounds. "
            user_prompt += (
                "Consider this structural relationship when evaluating whether the "
                "target compound performs the same function in the same way to achieve "
                "the same result as the claimed element."
            )

    if prosecution_context:
        user_prompt += (
            "\n\nPROSECUTION HISTORY CONTEXT (US file wrapper — for Festo analysis):\n"
            + sanitize_untrusted_text(
                prosecution_context,
                max_len=_PROSECUTION_CONTEXT_CAP,
                data_type="prosecution_history",
            )
            + "\n"
            "Use this record to determine whether narrowing amendments or "
            "surrendered scope create prosecution-history estoppel that bars DoE, "
            "and whether a Festo rebuttal (unforeseeability, tangentiality, "
            "other reason) is available."
        )

    return user_prompt


async def assess_fwr(
    claude: ClaudeClient,
    candidate: DoECandidate,
    compound: ResolvedCompound,
    system_prompt: str,
    drawing_evidence: DrawingEvidenceStore | None = None,
    prosecution_context: str | None = None,
) -> tuple[FWRAssessment, dict]:
    """Run the Function-Way-Result test on a single element."""
    fwr, usage = await claude.complete(
        system=system_prompt,
        user=build_fwr_user_prompt(
            candidate,
            compound,
            drawing_evidence=drawing_evidence,
            prosecution_context=prosecution_context,
        ),
        response_model=FWRAssessment,
        model=claude._models.deep,
        max_tokens=get_settings().doe_max_tokens,
        effort=get_settings().thinking_effort_analysis,
        cache_system=True,
        role="doe",
    )
    return fwr, usage


def derive_fwr_confidence(fwr: FWRAssessment | None, settings: Settings) -> float:
    """Map FWR prongs and known chemical relationships onto a confidence score."""
    if fwr is None:
        return settings.doe_fwr_fallback
    if any(value is None for value in (fwr.same_function, fwr.same_way, fwr.same_result)):
        return min(settings.doe_fwr_fallback, settings.doe_confidence_moderate - 0.01)

    prong_scores = [
        1.0 if fwr.same_function else 0.0,
        1.0 if fwr.same_way else 0.0,
        1.0 if fwr.same_result else 0.0,
    ]
    confidence = round(sum(prong_scores) / 3 * settings.doe_fwr_scale, 2)

    if (
        fwr.chemical_context
        and fwr.chemical_context.known_interchangeability
        and bool(fwr.chemical_context.interchangeability_evidence.strip())
    ):
        confidence = min(settings.doe_fwr_cap, confidence + settings.doe_fwr_boost)

    return confidence


def map_confidence_band(confidence: float, settings: Settings) -> ConfidenceBand:
    """Collapse the numeric FWR confidence into the report-facing 3-band label."""
    if confidence >= settings.doe_confidence_high:
        return "HIGH"
    if confidence >= settings.doe_confidence_moderate:
        return "MODERATE"
    return "LOW"


def build_doe_assessment(
    candidate: DoECandidate,
    estoppel: EstoppelResult,
    settings: Settings,
    *,
    fwr: FWRAssessment | None = None,
    prosecution_context_used: bool = False,
) -> DoEAssessment:
    """Assemble the final DoE assessment object for one candidate."""
    audit_suffix = " [prosecution_dossier=consulted]" if prosecution_context_used else ""
    if estoppel.estoppel_applies is True:
        return DoEAssessment(
            patent_id=candidate["patent_id"],
            claim_number=candidate["claim_number"],
            element_number=candidate["element_number"],
            element_text=candidate["element_text"],
            estoppel=estoppel,
            fwr=None,
            overall_equivalent=False,
            reasoning="Prosecution history estoppel bars DoE for this element." + audit_suffix,
        )

    confidence = derive_fwr_confidence(fwr, settings)
    reasoning_core = (
        f"FWR test: function={fwr.same_function}, way={fwr.same_way}, result={fwr.same_result}"
        if fwr
        else "Estoppel applies"
    )
    return DoEAssessment(
        patent_id=candidate["patent_id"],
        claim_number=candidate["claim_number"],
        element_number=candidate["element_number"],
        element_text=candidate["element_text"],
        estoppel=estoppel,
        fwr=fwr,
        overall_equivalent=(
            fwr.equivalent if fwr is not None and estoppel.estoppel_applies is False else None
        ),
        confidence=confidence,
        confidence_band=map_confidence_band(confidence, settings),
        reasoning=reasoning_core + audit_suffix,
    )

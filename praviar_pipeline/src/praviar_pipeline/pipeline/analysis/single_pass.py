"""Single-pass claim-analysis stage used inside the adaptive Step 4 path."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.pipeline.analysis.context_binding import (
    analysis_context_json,
    analysis_context_sha256,
)
from praviar_pipeline.sanitize import sanitize_untrusted_text
from praviar_pipeline.utils.claim_parser import format_pre_parsed_claims, split_claims

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.triage import TriageResult
    from praviar_pipeline.tools import FTOToolkit

logger = structlog.get_logger()


def _build_single_pass_user_prompt(
    patent: PatentHit,
    compound: ResolvedCompound,
    triage: TriageResult | None,
    *,
    format_compound_for_analysis: Callable[[ResolvedCompound], str],
    format_patent_for_analysis: Callable[[PatentHit, TriageResult | None], str],
    spec_text: str,
    prosecution_context: dict[str, Any] | None,
    drawing_evidence: DrawingEvidenceStore | None,
    toolkit: FTOToolkit | None,
    product_context: object = None,
    intended_actions: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
    development_stage: object = None,
) -> str:
    compound_ctx = format_compound_for_analysis(compound)
    patent_ctx = format_patent_for_analysis(patent, triage)

    pre_parsed_claims = split_claims(patent.claims_text or "")
    pre_parsed_section = ""
    if pre_parsed_claims:
        pre_parsed_section = (
            "\n\n--- PRE-PARSED CLAIM STRUCTURE ---\n\n"
            + sanitize_untrusted_text(
                format_pre_parsed_claims(pre_parsed_claims),
                data_type="pre_parsed_claims",
            )
            + "\n\n--- END PRE-PARSED CLAIMS ---\n\n"
        )
        logger.debug(
            "claims_pre_parsed",
            total_claims=len(pre_parsed_claims),
            independent=sum(1 for claim in pre_parsed_claims if claim.claim_type == "independent"),
        )

    user_prompt = (
        "Perform element-by-element claim analysis for the "
        "following patent against the target compound.\n\n"
        f"{compound_ctx}\n\n"
        "---\n\n"
        f"{patent_ctx}\n\n"
    )
    bound_context = analysis_context_json(
        patent_id=patent.patent_id,
        compound_identity=compound,
        product_context=product_context,
        intended_actions=intended_actions,
        target_jurisdictions=target_jurisdictions,
        development_stage=development_stage,
    )
    user_prompt += (
        "--- BOUND ACCUSED-INSTRUMENTALITY CONTEXT ---\n\n"
        + sanitize_untrusted_text(bound_context, data_type="product_context")
        + "\n\n--- END BOUND CONTEXT ---\n\n"
        "Assess every claim limitation against these exact product, use, process, "
        "actor, territory, timing, and development-stage facts. Missing facts are "
        "UNCLEAR, never inferred. Do not treat compound identity alone as proof of "
        "a method, process, dose, route, indication, patient, actor, or territorial "
        "limitation.\n\n"
    )

    if spec_text:
        user_prompt += (
            "--- SPECIFICATION EXCERPT (for claim term definitions) ---\n\n"
            + sanitize_untrusted_text(spec_text, data_type="patent_specification")
            + "\n\n"
            "--- END SPECIFICATION ---\n\n"
            "Use the specification above to interpret claim terms under the "
            "jurisdiction-specific doctrine stated in the system instructions. "
            "Definitions, examples, and preferred embodiments inform element "
            "scope but do not replace controlling claim language.\n\n"
        )

    if prosecution_context:
        prosecution_parts = ["--- PROSECUTION HISTORY CONTEXT ---\n"]
        if prosecution_context.get("office_actions"):
            prosecution_parts.append(
                "Office Actions (examiner rejections):\n"
                + sanitize_untrusted_text(
                    prosecution_context["office_actions"], data_type="office_actions"
                )
                + "\n"
            )
        if prosecution_context.get("amendments"):
            prosecution_parts.append(
                "Amendments & Responses (applicant narrowing):\n"
                + sanitize_untrusted_text(
                    prosecution_context["amendments"], data_type="prosecution_amendments"
                )
                + "\n"
            )
        if prosecution_context.get("continuity"):
            prosecution_parts.append(
                "Continuity Chain (priority / parent applications):\n"
                + sanitize_untrusted_text(
                    prosecution_context["continuity"], data_type="continuity_chain"
                )
                + "\n"
            )
        prosecution_parts.append("--- END PROSECUTION HISTORY ---\n")
        user_prompt += "\n".join(prosecution_parts) + "\n"

    if pre_parsed_section:
        user_prompt += pre_parsed_section
        user_prompt += (
            "The claims above have been pre-parsed into elements using "
            "deterministic syntactic analysis. Use this structure exactly. "
            "Do not re-parse, paraphrase, omit, or re-number the claims or elements. "
            "Reproduce each element_text verbatim, including Element 0 when present. "
            "For each element, assess whether the target compound/process "
            "meets it and provide your reasoning."
        )
    else:
        user_prompt += (
            "---\n\n"
            "Analyze each independent claim. For each claim, decompose "
            "into elements and assess whether each element is met by the "
            "target compound/process. Determine the overall risk level."
        )

    if drawing_evidence and drawing_evidence.has_structures(patent.patent_id):
        drawing_text = drawing_evidence.summary_for_prompt(
            patent.patent_id,
            max_structures=10,
            min_tanimoto=0.3,
        )
        if drawing_text:
            user_prompt += (
                "\n\n"
                + sanitize_untrusted_text(drawing_text, data_type="drawing_evidence_summary")
                + "\n\n"
                "When claims reference numbered figures, formulas, or compounds "
                "(e.g. 'compound of Formula I', 'as shown in FIG. 3'), "
                "cross-reference with the extracted structures above. "
                "The Tanimoto similarity and substructure match data provide "
                "quantitative structural evidence for your element-by-element assessment."
            )

    if toolkit:
        user_prompt += (
            "\n\nYou have access to tools for real-time data lookup. "
            "Use them if you need to verify patent dates, look up cited "
            "patents, or check prosecution status."
        )

    return user_prompt


def _finalize_single_pass_analysis(
    analysis: PatentAnalysis,
    *,
    patent_id: str,
    thinking_text: str,
    usage: dict,
    compute_risk_from_elements: Callable[[PatentAnalysis], RiskLevel],
    context_sha256: str,
) -> PatentAnalysis:
    analysis.model_used = usage["model"]
    analysis.thinking_text = thinking_text
    analysis.input_tokens = usage["input_tokens"]
    analysis.output_tokens = usage["output_tokens"]
    analysis.analysis_context_sha256 = context_sha256

    llm_risk = analysis.risk_level
    computed_risk = compute_risk_from_elements(analysis)
    if llm_risk != computed_risk:
        logger.info(
            "risk_level_overridden",
            llm_risk=llm_risk.value,
            computed_risk=computed_risk.value,
        )
        analysis.risk_level = computed_risk

    logger.debug(
        "single_pass_analysis_complete",
        thinking_length=len(thinking_text),
    )
    return analysis


async def analyze_single_patent_single_pass(
    claude: ClaudeClient,
    patent: PatentHit,
    compound: ResolvedCompound,
    triage: TriageResult | None,
    system_prompt: str,
    *,
    toolkit: FTOToolkit | None = None,
    drawing_evidence: DrawingEvidenceStore | None = None,
    spec_text: str = "",
    prosecution_context: dict[str, Any] | None = None,
    product_context: object = None,
    intended_actions: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
    development_stage: object = None,
    format_compound_for_analysis: Callable[[ResolvedCompound], str],
    format_patent_for_analysis: Callable[[PatentHit, TriageResult | None], str],
    compute_risk_from_elements: Callable[[PatentAnalysis], RiskLevel],
) -> PatentAnalysis:
    """Run the efficient single-pass stage of the adaptive analysis path."""
    settings = get_settings()
    user_prompt = _build_single_pass_user_prompt(
        patent,
        compound,
        triage,
        format_compound_for_analysis=format_compound_for_analysis,
        format_patent_for_analysis=format_patent_for_analysis,
        spec_text=spec_text,
        prosecution_context=prosecution_context,
        drawing_evidence=drawing_evidence,
        toolkit=toolkit,
        product_context=product_context,
        intended_actions=intended_actions,
        target_jurisdictions=target_jurisdictions,
        development_stage=development_stage,
    )

    analysis, thinking_text, usage = await claude.complete_with_thinking(
        system=system_prompt,
        user=user_prompt,
        response_model=PatentAnalysis,
        model=claude._models.deep,
        max_tokens=settings.analysis_max_tokens,
        budget_tokens=settings.analysis_thinking_budget_tokens,
        effort=settings.thinking_effort_analysis,
        json_schema=PatentAnalysis.model_json_schema(),
        toolkit=toolkit,
        cache_system=True,
        role="analysis",
    )

    return _finalize_single_pass_analysis(
        analysis,
        patent_id=patent.patent_id,
        thinking_text=thinking_text,
        usage=usage,
        compute_risk_from_elements=compute_risk_from_elements,
        context_sha256=analysis_context_sha256(
            patent_id=patent.patent_id,
            compound_identity=compound,
            product_context=product_context,
            intended_actions=intended_actions,
            target_jurisdictions=target_jurisdictions,
            development_stage=development_stage,
        ),
    )

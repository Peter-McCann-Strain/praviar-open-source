"""Agentic claim-analysis escalation stage for the adaptive Step 4 path."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError

from praviar_pipeline.clients.claude import _extract_json
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import LLMResponseError
from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.pipeline.analysis.context_binding import (
    analysis_context_json,
    analysis_context_sha256,
)
from praviar_pipeline.sanitize import sanitize_prompt_value, sanitize_untrusted_text
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Callable

    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit
    from praviar_pipeline.models.reasoning import ReasoningTrace
    from praviar_pipeline.models.triage import TriageResult

logger = structlog.get_logger()


async def analyze_single_patent_agentic(
    claude: ClaudeClient,
    patent: PatentHit,
    compound: ResolvedCompound,
    triage: TriageResult | None,
    *,
    format_compound_for_analysis: Callable[[ResolvedCompound], str],
    format_patent_for_analysis: Callable[[PatentHit, TriageResult | None], str],
    compute_risk_from_elements: Callable[[PatentAnalysis], RiskLevel],
    product_context: object = None,
    intended_actions: list[str] | None = None,
    target_jurisdictions: list[str] | None = None,
    development_stage: object = None,
) -> tuple[PatentAnalysis, ReasoningTrace]:
    """Run the research-agent escalation stage for one high-stakes patent."""
    from praviar_pipeline.agents.claim_analysis import ClaimAnalysisAgent

    compound_context = format_compound_for_analysis(compound)
    patent_context = format_patent_for_analysis(patent, triage)
    context = {
        "patent_id": patent.patent_id,
        "compound_context": compound_context,
        "patent_context": patent_context,
        "claims_text": patent.claims_text or "",
        "patent_data": {patent.patent_id: patent.model_dump(mode="json")},
        "bound_analysis_context": analysis_context_json(
            patent_id=patent.patent_id,
            compound_identity=compound,
            product_context=product_context,
            intended_actions=intended_actions,
            target_jurisdictions=target_jurisdictions,
            development_stage=development_stage,
        ),
    }

    agent = ClaimAnalysisAgent(claude)
    task = f"Analyze patent {patent.patent_id} for FTO risk against {compound.name}"

    research_findings, trace = await agent.research(task, context)

    settings = get_settings()
    schema_hint = """\
Output a single JSON object with EXACTLY these field names (no extras at the top level):
{
  "patent_id": "<string>",
  "title": "<string>",
  "assignee": "<string>",
  "expiry_date": "<YYYY-MM-DD or null>",
  "risk_level": "<high|medium|low|clear>",
  "risk_summary": "<string>",
  "claims_analyzed": [
    {
      "claim_number": <integer — number only, e.g. 1>,
      "claim_type": "<independent|dependent>",
      "depends_on": <integer or null>,
      "preamble": "<string>",
      "preamble_limiting": "<limiting|nonlimiting|unresolved>",
      "preamble_limitation_reasoning": "<jurisdiction-specific grounded reasoning>",
      "preamble_limitation_evidence": "<grounded citation or unresolved basis>",
      "transitional_phrase": "<comprising|consisting of|consisting essentially of or null>",
      "elements": [
        {
          "element_number": <integer; use 0 for a pre-parsed preamble>,
          "element_text": "<verbatim pre-parsed limitation text; do not paraphrase>",
          "status": "<met|not_met|partially_met|unclear>",
          "reasoning": "<string>",
          "confidence": <0.0-1.0>,
          "evidence": "<string>"
        }
      ],
      "overall_status": "<met|not_met|partially_met|unclear>",
      "overall_confidence": <0.0-1.0>,
      "reasoning": "<string>"
    }
  ],
  "design_around_suggestions": [
    {
      "element_avoided": <integer — which claim element number this suggestion avoids>,
      "suggestion": "<string describing the structural modification>",
      "feasibility": "<optional string assessing chemical viability>"
    }
  ]
}"""
    extraction_prompt = (
        "Based on your research findings below, output the final claim analysis as JSON.\n\n"
        f"{schema_hint}\n\n"
        + sanitize_untrusted_text(
            research_findings,
            max_len=60000,
            data_type="model_research_findings",
        )
        + "\n\n"
        f"Patent: {sanitize_prompt_value(patent.patent_id)}\n"
        f"Compound: {sanitize_prompt_value(compound.name)}\n"
        + sanitize_untrusted_text(patent.claims_text or "", data_type="claims_text")
    )
    system_prompt = claude.load_prompt("claim_analysis_system.txt")
    # Use complete_text + manual JSON parsing to avoid compiled-grammar size limits
    # that occur when PatentAnalysis's schema is passed as output_format.
    raw_text, extract_usage = await claude.complete_text(
        system=system_prompt,
        user=extraction_prompt,
        model=settings.claude_triage_model,
        max_tokens=8192,
        effort=settings.thinking_effort_analysis,
        cache_system=True,
        role="analysis",
    )
    parse_failure_type: str | None = None
    try:
        analysis = PatentAnalysis.model_validate_json(_extract_json(raw_text))
    except (ValidationError, LLMResponseError) as exc:
        parse_failure_type = safe_exception_type(exc)
        logger.warning(
            "analysis_extraction_json_failed",
            error_type=parse_failure_type,
        )
    analysis.analysis_context_sha256 = analysis_context_sha256(
        patent_id=patent.patent_id,
        compound_identity=compound,
        product_context=product_context,
        intended_actions=intended_actions,
        target_jurisdictions=target_jurisdictions,
        development_stage=development_stage,
    )
    if parse_failure_type is not None:
        raise LLMResponseError(
            "Analysis extraction failed",
            model=settings.claude_triage_model,
            step="analysis",
        ) from None

    analysis.model_used = agent.model_id
    analysis.thinking_text = trace.self_critique or ""
    analysis.input_tokens = trace.total_input_tokens + extract_usage.get("input_tokens", 0)
    analysis.output_tokens = trace.total_output_tokens + extract_usage.get("output_tokens", 0)

    computed_risk = compute_risk_from_elements(analysis)
    if analysis.risk_level != computed_risk:
        logger.info(
            "risk_level_overridden",
            llm_risk=analysis.risk_level.value,
            computed_risk=computed_risk.value,
        )
        analysis.risk_level = computed_risk

    return analysis, trace

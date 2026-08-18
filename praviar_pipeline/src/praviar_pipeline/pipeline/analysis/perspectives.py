"""Multi-perspective analysis helpers for Step 4."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.config import get_settings
from praviar_pipeline.models.analysis import (
    MultiPerspectiveSynthesis,
    PatentAnalysis,
    PerspectiveAnalysis,
    PerspectiveType,
)
from praviar_pipeline.sanitize import sanitize_prompt_value, sanitize_untrusted_text
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.clients.claude import ClaudeClient
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


async def run_perspectives(
    claude: ClaudeClient,
    patent: PatentHit,
    compound: ResolvedCompound,
    base_analysis: PatentAnalysis,
    compound_ctx: str,
    patent_ctx: str,
) -> list[PerspectiveAnalysis]:
    """Run three perspective agents in parallel for a patent."""
    from praviar_pipeline.agents.perspective import PerspectiveAgent

    settings = get_settings()
    semaphore = asyncio.Semaphore(settings.perspective_concurrency)
    perspectives = [
        PerspectiveType.PATENT_ATTORNEY,
        PerspectiveType.MEDICINAL_CHEMIST,
        PerspectiveType.BUSINESS_ANALYST,
    ]

    base_summary = (
        f"Patent: {base_analysis.patent_id}\n"
        f"Risk Level: {base_analysis.risk_level.value}\n"
        f"Risk Summary: {base_analysis.risk_summary}\n"
        f"Claims Analyzed: {len(base_analysis.claims_analyzed)}\n"
    )
    for claim in base_analysis.claims_analyzed[:5]:
        base_summary += f"  Claim {claim.claim_number}: {claim.overall_status.value}\n"

    context = {
        "patent_id": patent.patent_id,
        "compound_context": compound_ctx,
        "patent_context": patent_ctx,
        "base_analysis_summary": base_summary,
        "patent_data": {patent.patent_id: patent.model_dump(mode="json")},
    }

    async def _run_one(perspective: PerspectiveType) -> PerspectiveAnalysis:
        async with semaphore:
            agent = PerspectiveAgent(claude, perspective.value)
            task = (
                "Analyze the supplied patent evidence from the "
                f"{perspective.value.replace('_', ' ')} perspective for FTO risk."
            )
            try:
                findings, _trace = await agent.research(task, context)
                perspective_analysis, _ = await claude.complete(
                    system=(
                        "Extract the perspective analysis from the research findings below. "
                        "Output a structured JSON with: perspective, key_findings, "
                        "risk_assessment, "
                        "confidence, recommended_risk_level, evidence_cited."
                    ),
                    user=(
                        f"Perspective: {perspective.value}\n\n"
                        + sanitize_untrusted_text(
                            findings,
                            max_len=40000,
                            data_type="model_perspective_findings",
                        )
                    ),
                    response_model=PerspectiveAnalysis,
                    model=settings.claude_triage_model,
                    max_tokens=settings.perspective_max_tokens,
                    effort=settings.thinking_effort_analysis,
                    cache_system=True,
                )
                if perspective is not PerspectiveType.PATENT_ATTORNEY:
                    # Chemistry and business perspectives are evidence lanes, not
                    # alternative legal decision-makers.  Keep any model-emitted
                    # label from contaminating synthesis or report consumers.
                    perspective_analysis.recommended_risk_level = None
                return perspective_analysis
            except Exception as exc:
                logger.warning(
                    "perspective_agent_failed",
                    perspective=perspective.value,
                    error_type=safe_exception_type(exc),
                )
                return PerspectiveAnalysis(
                    perspective=perspective,
                    key_findings=["Perspective analysis failed — see logs"],
                    risk_assessment="Unable to assess",
                    confidence=0.0,
                )

    results = await asyncio.gather(*[_run_one(perspective) for perspective in perspectives])
    return list(results)


async def synthesize_perspectives(
    claude: ClaudeClient,
    perspectives: list[PerspectiveAnalysis],
    base_analysis: PatentAnalysis,
) -> MultiPerspectiveSynthesis:
    """Synthesize multiple perspective analyses into a unified assessment."""
    settings = get_settings()

    perspectives_text = ""
    for perspective in perspectives:
        recommended_risk = (
            perspective.recommended_risk_level.value
            if perspective.recommended_risk_level
            else "N/A"
        )
        perspectives_text += (
            f"\n### {perspective.perspective.value.replace('_', ' ').title()}\n"
            f"Risk Assessment: {perspective.risk_assessment}\n"
            f"Recommended Risk: {recommended_risk}\n"
            f"Confidence: {perspective.confidence}\n"
            f"Key Findings:\n"
        )
        for finding in perspective.key_findings:
            perspectives_text += f"  - {finding}\n"

    system_prompt = claude.load_prompt("perspective_synthesis_system.txt")
    synthesis, _ = await claude.complete(
        system=system_prompt,
        user=(
            f"Patent: {sanitize_prompt_value(base_analysis.patent_id)}\n"
            f"Base Risk Level: {base_analysis.risk_level.value}\n\n"
            "Expert Perspectives:\n"
            + sanitize_untrusted_text(perspectives_text, data_type="model_perspectives")
        ),
        response_model=MultiPerspectiveSynthesis,
        model=settings.claude_triage_model,
        max_tokens=4096,
        effort=settings.thinking_effort_analysis,
        cache_system=True,
    )
    synthesis.perspectives = perspectives
    # The synthesis is explanatory and must not create a second legal decision.
    # The governed base analysis remains the only source of the claim/status
    # risk field; downstream deterministic decisioning handles matter-level risk.
    synthesis.synthesized_risk = base_analysis.risk_level
    return synthesis

"""Step 3: LLM Triage — classify patents before adaptive claim analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.config import get_settings, get_triage_local_settings
from praviar_pipeline.models.triage import Relevance, TriageBatch, TriageResult
from praviar_pipeline.pipeline.drawing_rollout import (
    drawing_evidence_can_influence,
    drawing_rollout_state,
)
from praviar_pipeline.pipeline.triage import run_llm_triage_batches
from praviar_pipeline.pipeline.triage.drawing_filters import auto_triage_with_drawings
from praviar_pipeline.pipeline.triage.prompting import (
    build_triage_user_prompt,
    format_patent_for_triage,
)
from praviar_pipeline.sanitize import sanitize_patent_text
from praviar_pipeline.utils.formatting import format_compound_context

if TYPE_CHECKING:
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.models.patent import PatentHit

logger = structlog.get_logger()


def _format_patent_for_triage(patent: PatentHit, drawing_summary: str = "") -> str:
    """Format a patent hit for the triage prompt."""
    settings = get_triage_local_settings()
    return format_patent_for_triage(
        patent,
        max_abstract=settings.triage_max_abstract_chars,
        max_claims=settings.triage_max_claims_chars,
        drawing_summary=drawing_summary,
    )


def _auto_triage_with_drawings(
    patents: list[PatentHit],
    drawing_evidence: DrawingEvidenceStore,
) -> tuple[list[TriageResult], list[PatentHit]]:
    """Classify patents using drawing evidence alone, bypassing LLM.

    Returns:
        (auto_results, remaining_patents) — auto_results are patents classified
        without LLM, remaining_patents need LLM triage.
    """

    settings = get_triage_local_settings()
    return auto_triage_with_drawings(
        patents,
        drawing_evidence,
        settings=settings,
    )


async def _triage_batch(
    claude: ClaudeClient,
    patents: list[PatentHit],
    compound: ResolvedCompound,
    system_prompt: str,
    max_tokens: int,
    drawing_evidence: DrawingEvidenceStore | None = None,
) -> TriageBatch:
    """Triage a single batch of patents."""
    compound_ctx = format_compound_context(compound)

    # Format each patent, injecting drawing summary if available (Tier 3 enrichment).
    # Patent claims, abstracts and drawing summaries are external untrusted text
    # — sanitize at the LLM-call boundary to neutralise prompt-injection attempts.
    formatted_patents = []
    triage_settings = get_triage_local_settings()
    allow_drawing_evidence = drawing_evidence_can_influence(triage_settings)
    for p in patents:
        drawing_summary = ""
        if (
            allow_drawing_evidence
            and drawing_evidence
            and drawing_evidence.has_structures(p.patent_id)
        ):
            drawing_summary = sanitize_patent_text(drawing_evidence.brief_summary(p.patent_id))
        formatted_patent = _format_patent_for_triage(p, drawing_summary=drawing_summary)
        formatted_patents.append(sanitize_patent_text(formatted_patent))
    user_prompt = build_triage_user_prompt(compound_ctx, formatted_patents)

    effort = getattr(get_settings(), "thinking_effort_triage", None)
    batch, usage = await claude.complete(
        system=system_prompt,
        user=user_prompt,
        response_model=TriageBatch,
        model=claude._models.triage,
        max_tokens=max_tokens,
        effort=effort,
        cache_system=True,
        role="triage",
    )

    batch.model_used = usage["model"]
    batch.input_tokens = usage["input_tokens"]
    batch.output_tokens = usage["output_tokens"]

    return batch


async def triage_patents(
    patents: list[PatentHit],
    compound: ResolvedCompound,
    drawing_evidence: DrawingEvidenceStore | None = None,
) -> tuple[list[TriageResult], int, int, int, list[TriageResult]]:
    """Triage all patents in batches, return only relevant/possibly-relevant ones.

    Uses a three-tier approach when drawing evidence is available and the
    drawing rollout state is beta/production:
    - Tier 1: Auto-RELEVANT for high Tanimoto + substructure match (skip LLM)
    - Tier 2: Auto-NOT_RELEVANT for low Tanimoto + confident extraction (skip LLM)
    - Tier 3: LLM triage with drawing evidence injected into prompt

    Returns:
        Tuple of (filtered_results, input_tokens, output_tokens, failed_patent_count, all_results).
    """
    if not patents:
        # Zero input usually means upstream search returned no hits.
        # Surface this at WARNING level so an operator can diagnose a search
        # failure rather than silently producing an empty triage result.
        logger.warning(
            "step3_received_zero_input",
            patent_count=0,
        )
        logger.debug("step3_entry", patent_count=0)
        return [], 0, 0, 0, []

    logger.info("triage_start", patent_count=len(patents))

    # Drawing-based auto-filter (Tiers 1 & 2).
    auto_results: list[TriageResult] = []
    llm_patents = patents  # Default: all patents go to LLM
    triage_settings = get_triage_local_settings()
    allow_drawing_evidence = drawing_evidence_can_influence(triage_settings)

    if drawing_evidence and len(drawing_evidence) > 0 and allow_drawing_evidence:
        auto_results, llm_patents = _auto_triage_with_drawings(patents, drawing_evidence)
    elif drawing_evidence and len(drawing_evidence) > 0:
        logger.info(
            "triage_drawing_evidence_shadowed",
            rollout_state=drawing_rollout_state(triage_settings),
            patents_with_drawing_evidence=len(drawing_evidence),
        )

    if not llm_patents:
        all_results = auto_results
        filtered = [
            r
            for r in all_results
            if r.relevance in (Relevance.RELEVANT, Relevance.POSSIBLY_RELEVANT)
        ]
        auto_relevant = sum(1 for r in auto_results if r.relevance == Relevance.RELEVANT)
        auto_not_relevant = sum(1 for r in auto_results if r.relevance == Relevance.NOT_RELEVANT)
        logger.info(
            "triage_complete",
            total_classified=len(all_results),
            relevant=auto_relevant,
            possibly_relevant=0,
            not_relevant=auto_not_relevant,
            auto_relevant=auto_relevant,
            auto_not_relevant=auto_not_relevant,
            llm_triaged=0,
            patents_failed=0,
            input_tokens=0,
            output_tokens=0,
        )
        logger.debug(
            "step3_output_summary",
            filtered_count=len(filtered),
            total_classified=len(all_results),
            batches_total=0,
            batches_failed=0,
            total_input_tokens=0,
            total_output_tokens=0,
        )
        return filtered, 0, 0, 0, all_results

    settings = get_settings()
    logger.debug(
        "step3_entry",
        patent_count=len(patents),
        batch_size=settings.triage_batch_size,
        concurrency=settings.triage_concurrency,
    )

    async with ClaudeClient() as claude:
        system_prompt = claude.load_prompt("triage_system.txt")
        triage_run = await run_llm_triage_batches(
            claude=claude,
            llm_patents=llm_patents,
            known_patent_ids={patent.patent_id for patent in patents},
            compound=compound,
            system_prompt=system_prompt,
            settings=settings,
            auto_results=auto_results,
            drawing_evidence=drawing_evidence,
            triage_batch_fn=_triage_batch,
        )
        filtered = triage_run.filtered
        total_input = triage_run.total_input
        total_output = triage_run.total_output
        failed_patent_count = triage_run.failed_patent_count
        all_results = triage_run.all_results

        auto_relevant = sum(1 for r in auto_results if r.relevance == Relevance.RELEVANT)
        auto_not_relevant = sum(1 for r in auto_results if r.relevance == Relevance.NOT_RELEVANT)
        logger.info(
            "triage_complete",
            total_classified=len(all_results),
            relevant=sum(1 for r in all_results if r.relevance == Relevance.RELEVANT),
            possibly_relevant=sum(
                1 for r in all_results if r.relevance == Relevance.POSSIBLY_RELEVANT
            ),
            not_relevant=sum(1 for r in all_results if r.relevance == Relevance.NOT_RELEVANT),
            unknown=sum(1 for r in all_results if r.relevance == Relevance.UNKNOWN),
            auto_relevant=auto_relevant,
            auto_not_relevant=auto_not_relevant,
            llm_triaged=len(llm_patents),
            patents_failed=failed_patent_count,
            input_tokens=total_input,
            output_tokens=total_output,
        )

        logger.debug(
            "step3_output_summary",
            filtered_count=len(filtered),
            total_classified=len(all_results),
            batches_total=triage_run.batch_count,
            batches_failed=triage_run.failed_batch_count,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
        )

        return filtered, total_input, total_output, failed_patent_count, all_results

"""Step 5: Doctrine of Equivalents coordination."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.clients.claude import ClaudeClient
from praviar_pipeline.config import get_settings
from praviar_pipeline.errors import DoEAssessmentError
from praviar_pipeline.models.equivalents import DoEAssessment, EstoppelResult
from praviar_pipeline.pipeline.doe import (
    assess_fwr as _assess_fwr,
)
from praviar_pipeline.pipeline.doe import (
    build_doe_assessment,
    build_prosecution_context_summary,
    rank_and_limit_candidates,
)
from praviar_pipeline.pipeline.doe import (
    check_estoppel as _check_estoppel,
)
from praviar_pipeline.pipeline.doe import (
    find_doe_candidates as _find_doe_candidates,
)
from praviar_pipeline.pipeline.doe.design_around_validation import validate_design_around
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.compound import ResolvedCompound
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.pipeline.doe.candidates import DoECandidate

logger = structlog.get_logger()


def _is_us_patent(patent_id: str) -> bool:
    """Prosecution-history estoppel analysis is US-specific (Festo, 2002)."""
    return patent_id.upper().startswith("US")


def _build_prosecution_summaries(
    unique_patents: list[str],
    prosecution_cache: dict[str, dict[str, Any]] | None,
) -> dict[str, str]:
    """Build per-patent prosecution-context summary strings for US patents only."""
    if not prosecution_cache:
        return {}
    summaries: dict[str, str] = {}
    for patent_id in unique_patents:
        if not _is_us_patent(patent_id):
            continue
        context = prosecution_cache.get(patent_id)
        if not context:
            continue
        summary = build_prosecution_context_summary(context)
        if summary:
            summaries[patent_id] = summary
    us_patents_in_candidates = [pid for pid in unique_patents if _is_us_patent(pid)]
    missing = [pid for pid in us_patents_in_candidates if pid not in summaries]
    if summaries:
        logger.info(
            "doe_prosecution_dossier_attached",
            us_patents_with_dossier=len(summaries),
        )
    if missing:
        # Step 4 enrichment records SourceHealth for uspto_odp failures;
        # here we log a DoE-specific warning that the LLM will run without
        # the Festo-relevant dossier for these US patents.
        logger.warning(
            "doe_prosecution_dossier_missing",
            source="uspto_odp_filewrapper",
        )
    return summaries


def _validate_design_around_suggestions(
    analyses: list[PatentAnalysis],
    original_smiles: str,
) -> list[PatentAnalysis]:
    """Run feasibility validation on any design-around suggestions that carry a SMILES.

    Iterates over every :class:`~praviar_pipeline.models.analysis_patent.PatentAnalysis`
    in the list.  For each :class:`~praviar_pipeline.models.analysis_claims.DesignAroundSuggestion`
    that has a ``smiles`` field set, calls
    :func:`~praviar_pipeline.pipeline.doe.design_around_validation.validate_design_around`
    to populate ``rdkit_valid``, ``tanimoto_to_original``, and
    ``pharmacophore_preserved``.  Suggestions without a SMILES are left unchanged.

    Returns a new list of :class:`~praviar_pipeline.models.analysis_patent.PatentAnalysis`
    instances (via ``model_copy``) so the input list is not mutated.  Analyses
    that have no SMILES-bearing suggestions are returned as-is.
    """
    updated: list[PatentAnalysis] = []
    for analysis in analyses:
        if not any(s.smiles for s in analysis.design_around_suggestions):
            updated.append(analysis)
            continue

        validated_suggestions = [
            validate_design_around(s, original_smiles) if s.smiles is not None else s
            for s in analysis.design_around_suggestions
        ]
        updated.append(
            analysis.model_copy(update={"design_around_suggestions": validated_suggestions})
        )

    validated_count = sum(
        1 for a in updated for s in a.design_around_suggestions if s.rdkit_valid is not None
    )
    if validated_count:
        logger.info(
            "design_around_validation_complete",
            validated_suggestions=validated_count,
        )
    return updated


async def assess_equivalents(
    analyses: list[PatentAnalysis],
    compound: ResolvedCompound,
    drawing_evidence: DrawingEvidenceStore | None = None,
    prosecution_cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[DoEAssessment], int, int]:
    """Assess Doctrine of Equivalents for all NOT_MET elements in blocking patents."""
    if not analyses:
        # Zero input means step4 produced no analyses (search/triage upstream
        # likely returned nothing). Warn so an operator can diagnose.
        logger.warning(
            "step5_received_zero_input",
            analyses_count=0,
        )
    # Validate any design-around suggestions that carry a proposed SMILES.
    # This is done before candidate selection so validated analyses propagate
    # to all downstream consumers (DoE, report rendering, critic).
    if compound.canonical_smiles:
        analyses = _validate_design_around_suggestions(analyses, compound.canonical_smiles)

    candidates = _find_doe_candidates(analyses)
    logger.debug(
        "step5_entry",
        analyses_count=len(analyses),
        candidates_found=len(candidates),
    )

    if not candidates:
        logger.info("doe_no_candidates")
        return [], 0, 0

    logger.info(
        "doe_assessment_start",
        candidate_count=len(candidates),
    )

    settings = get_settings()
    candidates = rank_and_limit_candidates(candidates, analyses, settings.max_doe_candidates)

    async with ClaudeClient() as claude:
        system_prompt = claude.load_prompt("doe_fwr_screening_system.txt")

        unique_patents = list({c["patent_id"] for c in candidates})
        # Build prosecution dossier summaries for US patents before LLM calls.
        # Cache comes from Step 4 enrichment (fetch_prosecution_context_impl),
        # which short-circuits non-US patents and records SourceHealth itself.
        prosecution_summaries = _build_prosecution_summaries(unique_patents, prosecution_cache)
        # Use a small bounded fan-out because prosecution history is network-bound.
        sem = asyncio.Semaphore(5)

        async def _limited_check(pid: str) -> tuple[str, EstoppelResult]:
            async with sem:
                return pid, await _check_estoppel(pid)

        estoppel_pairs = await asyncio.gather(*[_limited_check(pid) for pid in unique_patents])
        estoppel_results: dict[str, EstoppelResult] = dict(estoppel_pairs)

        semaphore = asyncio.Semaphore(settings.doe_concurrency)
        assessments = []
        failures: list[BaseException] = []
        total_input = 0
        total_output = 0

        async def _process_candidate(
            candidate: DoECandidate,
        ) -> tuple[DoEAssessment, int, int]:
            estoppel = estoppel_results.get(candidate["patent_id"], EstoppelResult())
            prosecution_context = prosecution_summaries.get(candidate["patent_id"])
            prosecution_used = bool(prosecution_context)

            if estoppel.estoppel_applies:
                return (
                    build_doe_assessment(
                        candidate,
                        estoppel,
                        settings,
                        prosecution_context_used=prosecution_used,
                    ),
                    0,
                    0,
                )

            async with semaphore:
                fwr, usage = await _assess_fwr(
                    claude,
                    candidate,
                    compound,
                    system_prompt,
                    drawing_evidence=drawing_evidence,
                    prosecution_context=prosecution_context,
                )

            return (
                build_doe_assessment(
                    candidate,
                    estoppel,
                    settings,
                    fwr=fwr,
                    prosecution_context_used=prosecution_used,
                ),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )

        results = await asyncio.gather(
            *[_process_candidate(c) for c in candidates],
            return_exceptions=True,
        )

        for r in results:
            if isinstance(r, BaseException):
                failures.append(r)
                logger.error(
                    "doe_candidate_failed",
                    error_type=safe_exception_type(r),
                )
            else:
                assessment, inp, out = r
                assessments.append(assessment)
                total_input += inp
                total_output += out

        if failures:
            raise DoEAssessmentError(
                failure_types=tuple(safe_exception_type(error) for error in failures),
            ) from None

        logger.info(
            "doe_assessment_complete",
            assessed=len(assessments),
            equivalent=sum(1 for a in assessments if a.overall_equivalent),
        )
        logger.debug(
            "step5_output_summary",
            assessed=len(assessments),
            equivalent_count=sum(1 for a in assessments if a.overall_equivalent),
            estoppel_applied=sum(1 for a in assessments if a.estoppel.estoppel_applies),
            unique_patents=len({a.patent_id for a in assessments}),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
        )

        return assessments, total_input, total_output

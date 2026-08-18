"""Top-level orchestration helpers for patent drawing analysis."""

from __future__ import annotations

import asyncio
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from praviar_pipeline.errors import DrawingAnalysisError, DrawingExecutionError
from praviar_pipeline.models.drawing import DrawingAnalysisResults, PatentDrawingAnalysis
from praviar_pipeline.pipeline.drawing_rollout import (
    build_drawing_governance_provenance,
    drawing_evidence_can_influence,
    drawing_jurisdiction_allowlist,
    drawing_rollout_state,
    filter_patents_by_drawing_jurisdiction,
)
from praviar_pipeline.utils.private_artifacts import ensure_private_directory
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from praviar_pipeline.clients.epo_ops import EPOOPSClient
    from praviar_pipeline.config import Settings
    from praviar_pipeline.ocsr.runner import OCSRRunner, SegmentationRunner

logger = structlog.get_logger()


def resolve_work_dir(settings: Settings) -> Path:
    """Resolve the working directory for downloaded and rendered drawing assets."""
    cache_dir = settings.drawing_image_cache_dir
    if cache_dir:
        work_dir = Path(cache_dir)
        ensure_private_directory(work_dir)
        return work_dir
    return ensure_private_directory(Path(tempfile.mkdtemp(prefix="praviar_pipeline_drawings_")))


def select_patents_to_process(patent_hits: Sequence[Any], *, max_patents: int) -> list[Any]:
    """Apply the patent-processing limit while preserving input order."""
    if max_patents > 0:
        return list(patent_hits[:max_patents])
    return list(patent_hits)


def build_patent_text(patent: Any) -> str:
    """Combine abstract and claims text for downstream drawing analysis."""
    patent_text = getattr(patent, "abstract", "") or ""
    claims = getattr(patent, "claims_text", "") or ""
    if claims:
        patent_text = f"{patent_text}\n{claims}"
    return patent_text


async def create_epo_client(
    *,
    client_factory: Callable[[], EPOOPSClient],
) -> EPOOPSClient | None:
    """Create an EPO OPS client, swallowing recoverable environment/network failures."""
    try:
        return client_factory()
    except (httpx.HTTPError, ConnectionError, ValueError, OSError) as exc:
        logger.warning(
            "drawing_epo_client_failed",
            error_type=safe_exception_type(exc),
        )
        return None


async def close_epo_client(epo_client: EPOOPSClient | None) -> None:
    """Close the EPO client best-effort."""
    if epo_client:
        with suppress(httpx.HTTPError, OSError):
            await epo_client.close()


async def run_patent_analyses(
    patents_to_process: Sequence[Any],
    *,
    epo_client: EPOOPSClient | None,
    seg_runner: SegmentationRunner | None,
    all_runners: dict[str, OCSRRunner],
    compound_smiles: str,
    settings: Settings,
    work_dir: Path,
    analyze_single_patent_fn: Callable[..., Awaitable[PatentDrawingAnalysis]],
) -> list[PatentDrawingAnalysis]:
    """Run bounded concurrent drawing analysis over the selected patents."""
    semaphore = asyncio.Semaphore(settings.drawing_concurrency)

    async def _bounded_analyze(patent: Any) -> PatentDrawingAnalysis:
        async with semaphore:
            patent_id = getattr(patent, "patent_id", str(patent))
            try:
                return await asyncio.wait_for(
                    analyze_single_patent_fn(
                        patent_id=patent_id,
                        epo_client=epo_client,
                        seg_runner=seg_runner,
                        all_runners=all_runners,
                        target_smiles=compound_smiles,
                        settings=settings,
                        work_dir=work_dir,
                        patent_text=build_patent_text(patent),
                    ),
                    timeout=settings.drawing_timeout_per_patent_s,
                )
            except TimeoutError:
                logger.error(
                    "drawing_patent_timeout",
                    timeout_s=settings.drawing_timeout_per_patent_s,
                )
                raise DrawingAnalysisError(failure_types=("TimeoutError",)) from None
            except DrawingExecutionError as exc:
                logger.error(
                    "drawing_patent_stage_failed",
                    error_type=safe_exception_type(exc),
                )
                raise DrawingAnalysisError(
                    failure_types=(safe_exception_type(exc), *exc.failure_types),
                ) from None
            except (
                httpx.HTTPError,
                ConnectionError,
                RuntimeError,
                OSError,
                ValueError,
            ) as exc:
                logger.error(
                    "drawing_patent_failed",
                    error_type=safe_exception_type(exc),
                )
                raise DrawingAnalysisError(
                    failure_types=(safe_exception_type(exc),),
                ) from None

    raw_results = await asyncio.gather(
        *[_bounded_analyze(patent) for patent in patents_to_process],
        return_exceptions=True,
    )
    results: list[PatentDrawingAnalysis] = []
    failure_types: list[str] = []
    for _patent, result in zip(patents_to_process, raw_results, strict=False):
        if isinstance(result, BaseException):
            logger.error(
                "drawing_patent_failed_unhandled",
                error_type=safe_exception_type(result),
            )
            if isinstance(result, DrawingAnalysisError):
                failure_types.extend(result.failure_types)
            else:
                failure_types.append(safe_exception_type(result))
            continue
        results.append(result)
    if failure_types:
        raise DrawingAnalysisError(failure_types=tuple(failure_types)) from None
    return results


async def run_drawing_analysis(
    patent_hits: Sequence[Any],
    *,
    compound_smiles: str,
    settings: Settings,
    claude_client=None,
    claim_text_by_patent: dict[str, str] | None = None,
    rgroup_definitions_by_patent: dict[str, dict[str, list[str]]] | None = None,
    markush_scope_apply_fn=None,
    get_runners_fn,
    get_segmentation_runner_fn,
    create_epo_client_fn,
    resolve_work_dir_fn,
    select_patents_to_process_fn,
    run_patent_analyses_fn,
    close_epo_client_fn,
    build_results_fn,
) -> DrawingAnalysisResults:
    """Run the top-level Step 2.75 orchestration using injected stable wrappers."""
    if not settings.drawing_analysis_enabled:
        return DrawingAnalysisResults()

    governance_provenance = build_drawing_governance_provenance(settings)
    fail_closed = drawing_evidence_can_influence(settings)
    all_runners = get_runners_fn(settings.drawing_ensemble_tools, settings)
    if not all_runners:
        if fail_closed:
            raise RuntimeError("Drawing analysis is live but no OCSR tools are available")
        logger.error("drawing_no_runners")
        return DrawingAnalysisResults()

    seg_runner = get_segmentation_runner_fn()
    epo_client = await create_epo_client_fn()
    if fail_closed and seg_runner is None:
        raise RuntimeError("Drawing analysis is live but no segmentation runner is available")
    if fail_closed and epo_client is None:
        raise RuntimeError("Drawing analysis is live but EPO OPS access is unavailable")
    work_dir = resolve_work_dir_fn(settings)

    logger.info(
        "drawing_analysis_start",
        n_patents=len(patent_hits),
        tools=list(all_runners.keys()),
        cascade=settings.drawing_cascade_enabled,
        classifier=settings.drawing_classifier_enabled,
        text_validation=settings.drawing_text_validation_enabled,
        rollout_state=drawing_rollout_state(settings),
        jurisdiction_allowlist=drawing_jurisdiction_allowlist(settings),
    )

    patents_to_process = select_patents_to_process_fn(
        patent_hits,
        max_patents=settings.drawing_max_patents,
    )
    patents_to_process = filter_patents_by_drawing_jurisdiction(patents_to_process, settings)
    try:
        results = await run_patent_analyses_fn(
            patents_to_process,
            epo_client=epo_client,
            seg_runner=seg_runner,
            all_runners=all_runners,
            compound_smiles=compound_smiles,
            settings=settings,
            work_dir=work_dir,
        )
    finally:
        await close_epo_client_fn(epo_client)

    for analysis in results:
        analysis.governance_provenance = governance_provenance
    aggregate: DrawingAnalysisResults = build_results_fn(results)
    if settings.drawing_markush_scope_agent_enabled:
        from praviar_pipeline.pipeline.drawing_rollout import (
            markush_scope_agent_can_run,
        )

        if not markush_scope_agent_can_run(settings):
            raise RuntimeError(
                "Experimental Markush scope verdicts are shadow-only and cannot "
                "be attached to beta or production drawing evidence"
            )
        if markush_scope_apply_fn is None:
            from praviar_pipeline.pipeline.drawings.markush_scope_apply import (
                apply_markush_scope_verdicts,
            )

            markush_scope_apply_fn = apply_markush_scope_verdicts
        await markush_scope_apply_fn(
            aggregate,
            target_smiles=compound_smiles,
            claim_text_by_patent=claim_text_by_patent or {},
            claude=claude_client,
            settings=settings,
            rgroup_definitions_by_patent=rgroup_definitions_by_patent or {},
        )
    logger.info(
        "drawing_analysis_complete",
        patents_processed=len(results),
        patents_with_images=aggregate.total_patents_with_images,
        total_structures=aggregate.total_structures_extracted,
        high_risk=aggregate.total_high_risk_structures,
        total_time_s=aggregate.total_time_s,
    )
    return aggregate

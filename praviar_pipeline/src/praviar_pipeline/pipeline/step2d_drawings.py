"""Step 2.75: Patent Drawing Analysis — Full Option C Pipeline.

Complete pipeline for extracting and analyzing chemical structures from
patent drawings. The active runtime runs it on the post-triage relevant set,
before adaptive claim analysis.

Architecture (PatCID-style):
1. Fetch patent drawing pages from EPO OPS
2. Configured page segmentation (DECIMER by default) -> structure-region crops
3. Classify each crop: molecule / reaction / Markush / non-chemical
4. Adaptive preprocessing (jurisdiction-aware)
5. Confidence cascade OCSR (MolScribe first -> escalate if uncertain)
6. Safe postprocessing (salt removal, canonicalization)
7. Text cross-validation (formula, CAS, IUPAC vs OCSR output)
8. Tanimoto similarity to target compound
9. Risk scoring -> DrawingAnalysisResults

Each OCSR model runs in its own isolated venv via subprocess workers.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, cast

import structlog

from praviar_pipeline.clients.epo_ops import EPOOPSClient
from praviar_pipeline.ocsr.classifier_v2 import classify_image, configure_from_settings
from praviar_pipeline.ocsr.preprocessing import bytes_to_image, preprocess
from praviar_pipeline.ocsr.runner import OCSRRunner, SegmentationRunner
from praviar_pipeline.pipeline.drawing_rollout import drawing_evidence_can_influence
from praviar_pipeline.pipeline.drawings import factories as drawing_factories
from praviar_pipeline.pipeline.drawings import orchestration as drawing_orchestration
from praviar_pipeline.pipeline.drawings import patent_analysis as drawing_patent_analysis
from praviar_pipeline.pipeline.drawings import pdf_fallback as drawing_pdf_fallback
from praviar_pipeline.pipeline.drawings import references as drawing_references
from praviar_pipeline.pipeline.drawings import structure_analysis as drawing_structure_analysis
from praviar_pipeline.pipeline.drawings.cascade import run_cascade_ocsr as _run_cascade_ocsr
from praviar_pipeline.pipeline.drawings.chemistry import (
    check_substructure as _check_substructure,
)
from praviar_pipeline.pipeline.drawings.chemistry import (
    compute_tanimoto as _compute_tanimoto,
)
from praviar_pipeline.pipeline.drawings.preprocessing import (
    get_preprocessing_steps as _get_preprocessing_steps,
)
from praviar_pipeline.pipeline.drawings.preprocessing import (
    image_hash as _image_hash,
)
from praviar_pipeline.pipeline.drawings.preprocessing import (
    jurisdiction_from_patent_id as _jurisdiction_from_patent_id,
)
from praviar_pipeline.pipeline.drawings.tooling import (
    DRAWING_RESULT_CACHE,
    SEGMENTATION_BACKENDS,
    TOOL_CONFIGS,
)

if TYPE_CHECKING:
    from pathlib import Path

    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.drawing import (
        DrawingAnalysisResults,
        DrawingStructure,
        PatentDrawingAnalysis,
    )

logger = structlog.get_logger()

# Compatibility alias kept for existing tests and patch sites.
_result_cache = DRAWING_RESULT_CACHE


def _get_runners(tool_names: list[str], settings: Settings) -> dict[str, OCSRRunner]:
    """Create OCSR runners for the specified tools."""
    return drawing_factories.get_runners(
        tool_names,
        settings,
        tool_configs=TOOL_CONFIGS,
        logger=logger,
        runner_cls=OCSRRunner,
        fail_closed=drawing_evidence_can_influence(settings),
    )


def _get_segmentation_runner(settings: Settings) -> SegmentationRunner | None:
    """Create the configured segmentation runner.

    Backend is chosen by ``settings.drawing_segmentation_tool``. The reviewed
    default is ``decimer``; ``moldet`` uses a per-molecule YOLO11l detector but
    is restricted to non-commercial research, and ``chemsam`` is an optional
    SAM-based Markush-aware detector.
    """
    return cast(
        "SegmentationRunner | None",
        drawing_factories.get_segmentation_runner(
            backend=settings.drawing_segmentation_tool,
            backends=SEGMENTATION_BACKENDS,
            logger=logger,
            runner_cls=SegmentationRunner,
            fail_closed=drawing_evidence_can_influence(settings),
        ),
    )


async def _analyze_structure_image(
    image_path: Path,
    patent_id: str,
    page_number: int,
    structure_index: int,
    all_runners: dict[str, OCSRRunner],
    target_smiles: str,
    settings: Settings,
    patent_text: str = "",
) -> DrawingStructure | None:
    """Full analysis pipeline for a single structure image.

    Steps:
    1. Check result cache
    2. Classify image type
    3. Preprocess (jurisdiction-aware)
    4. Confidence cascade OCSR
    5. Postprocess (safe only: salt removal, canonicalization)
    6. Text cross-validation
    7. Compute similarity to target
    8. Risk scoring
    """
    prepared = await drawing_structure_analysis.prepare_structure_ocsr(
        image_path=image_path,
        patent_id=patent_id,
        page_number=page_number,
        structure_index=structure_index,
        all_runners=all_runners,
        settings=settings,
        patent_text=patent_text,
        result_cache=DRAWING_RESULT_CACHE,
        image_hash_fn=_image_hash,
        bytes_to_image_fn=bytes_to_image,
        classify_image_fn=classify_image,
        get_runners_fn=_get_runners,
        jurisdiction_from_patent_id_fn=_jurisdiction_from_patent_id,
        get_preprocessing_steps_fn=_get_preprocessing_steps,
        preprocess_fn=preprocess,
        run_cascade_ocsr_fn=_run_cascade_ocsr,
    )
    if prepared is None:
        return None
    if prepared.direct_structure is not None:
        return prepared.direct_structure

    fused = prepared.fused
    if not fused:
        return None
    if not fused.valid or not fused.smiles:
        return None

    return await drawing_structure_analysis.finalize_structure_analysis(
        fused=fused,
        image_path=image_path,
        patent_id=patent_id,
        page_number=page_number,
        structure_index=structure_index,
        target_smiles=target_smiles,
        settings=settings,
        patent_text=patent_text,
        applied_steps=prepared.applied_steps,
        input_image_sha256=prepared.input_image_sha256,
        compute_tanimoto_fn=_compute_tanimoto,
        check_substructure_fn=_check_substructure,
    )


cross_check_figure_references = drawing_references.cross_check_figure_references


_fetch_pdf_fallback = drawing_pdf_fallback.fetch_pdf_fallback


async def _analyze_single_patent(
    patent_id: str,
    epo_client: EPOOPSClient | None,
    seg_runner: SegmentationRunner | None,
    all_runners: dict[str, OCSRRunner],
    target_smiles: str,
    settings: Settings,
    work_dir: Path,
    patent_text: str = "",
) -> PatentDrawingAnalysis:
    """Full drawing analysis for a single patent."""
    return await drawing_patent_analysis.analyze_single_patent(
        patent_id=patent_id,
        epo_client=epo_client,
        seg_runner=seg_runner,
        all_runners=all_runners,
        target_smiles=target_smiles,
        settings=settings,
        work_dir=work_dir,
        patent_text=patent_text,
        fetch_pdf_fallback_fn=_fetch_pdf_fallback,
        analyze_structure_image_fn=_analyze_structure_image,
        figure_gap_fn=cross_check_figure_references,
    )


async def analyze_patent_drawings(
    patent_hits: list,
    compound_smiles: str,
    settings: Settings,
) -> DrawingAnalysisResults:
    """Run drawing analysis on patent hits.

    This is the main entry point called from run.py as Step 2.75.
    Implements the full Option C PatCID-style pipeline:
    fetch -> segment -> classify -> preprocess -> cascade OCSR -> postprocess
    -> text validate -> risk score.

    Args:
        patent_hits: List of PatentHit objects from search step.
        compound_smiles: Target compound SMILES for similarity comparison.
        settings: Pipeline settings.

    Returns:
        DrawingAnalysisResults with per-patent analysis.
    """
    # Forward Settings-driven thresholds to the workers and the ensemble layer
    # via env vars. Two bridges: the MolClassifier worker
    # (separate venv, can't import Settings) and the in-process fusion
    # helpers (read env to avoid threading Settings through pure functions).
    # Raises loudly if Settings is missing any required key.
    configure_from_settings(settings)
    from praviar_pipeline.ocsr.ensemble import (
        set_thresholds_from_settings as _ensemble_thresholds,
    )

    _ensemble_thresholds(settings)
    return await drawing_orchestration.run_drawing_analysis(
        patent_hits,
        compound_smiles=compound_smiles,
        settings=settings,
        get_runners_fn=_get_runners,
        # Orchestration calls ``get_segmentation_runner_fn()`` with no
        # arguments, so close over ``settings`` here to thread the
        # ``drawing_segmentation_tool`` flag through the dispatch helper.
        get_segmentation_runner_fn=lambda: _get_segmentation_runner(settings),
        create_epo_client_fn=lambda: drawing_orchestration.create_epo_client(
            client_factory=EPOOPSClient,
        ),
        resolve_work_dir_fn=drawing_orchestration.resolve_work_dir,
        select_patents_to_process_fn=drawing_orchestration.select_patents_to_process,
        run_patent_analyses_fn=partial(
            drawing_orchestration.run_patent_analyses,
            analyze_single_patent_fn=_analyze_single_patent,
        ),
        close_epo_client_fn=drawing_orchestration.close_epo_client,
        build_results_fn=drawing_structure_analysis.build_drawing_analysis_results,
    )

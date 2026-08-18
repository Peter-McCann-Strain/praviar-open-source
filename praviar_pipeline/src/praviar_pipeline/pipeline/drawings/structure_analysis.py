"""Helpers for finalizing drawing structure analysis results."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import httpx
import structlog

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.classifier_v2 import ImageCategory
from praviar_pipeline.ocsr.ensemble import apply_resolution_gates
from praviar_pipeline.ocsr.runner import OCSRExecutionError
from praviar_pipeline.ocsr.text_validation_helpers import extract_abbreviation_labels
from praviar_pipeline.pipeline.drawing_rollout import (
    LIVE_DRAWING_ROLLOUT_STATES,
    drawing_rollout_state,
    drawing_specialist_tool_can_emit,
)
from praviar_pipeline.pipeline.drawings.structure_analysis_helpers import (
    PreparedStructureOCSR,
    build_drawing_analysis_results,
    build_final_drawing_structure,
    build_markush_prepared_structure,
    build_patent_drawing_analysis,
    compute_risk_level,
    extract_text_formula_signal,
    extract_text_smiles_signal,
)
from praviar_pipeline.utils.private_artifacts import atomic_write_bytes
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

# Re-exports — older callers (e.g. step2d_drawings.py:250) reference
# `drawing_structure_analysis.build_drawing_analysis_results`. The function
# was moved to structure_analysis_helpers in an earlier refactor; we expose
# it here so the import path stays stable for callers and the formatter
# doesn't strip it as "unused".
__all__ = [
    "PreparedStructureOCSR",
    "build_drawing_analysis_results",
    "build_final_drawing_structure",
    "build_markush_prepared_structure",
    "build_patent_drawing_analysis",
    "compute_risk_level",
    "extract_text_formula_signal",
    "extract_text_smiles_signal",
]

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from pathlib import Path

    from PIL.Image import Image

    from praviar_pipeline.config import Settings
    from praviar_pipeline.models.drawing import DrawingStructure
    from praviar_pipeline.ocsr.classifier_v2 import ClassificationResult

logger = structlog.get_logger()


def _governed_markush_result(result: object, settings: Settings) -> OCSRResult | None:
    """Normalize and gate one specialist Markush result before persistence."""
    cxsmiles = str(getattr(result, "cxsmiles", "") or getattr(result, "smiles", ""))
    if not cxsmiles or getattr(result, "markush_validation", "") != "passed":
        return None
    candidate = OCSRResult(
        smiles=cxsmiles,
        cxsmiles=cxsmiles,
        confidence=float(getattr(result, "confidence", 0.0)),
        confidence_available=bool(getattr(result, "confidence_available", False)),
        valid=bool(getattr(result, "valid", False)),
        tool=str(getattr(result, "tool", "markushgrapher") or "markushgrapher"),
        is_markush=True,
        markush_validation="passed",
    )
    governed = apply_resolution_gates(
        candidate,
        min_resolved_conf=settings.drawing_cascade_min_resolved_conf,
        max_resolved_atoms=settings.drawing_max_resolved_atoms,
    )
    return governed if governed.valid and governed.smiles else None


async def prepare_structure_ocsr(
    *,
    image_path: Path,
    patent_id: str,
    page_number: int,
    structure_index: int,
    all_runners: Mapping[str, object],
    settings: Settings,
    patent_text: str,
    result_cache: dict[str, OCSRResult],
    image_hash_fn: Callable[[bytes], str],
    bytes_to_image_fn: Callable[[bytes], Image],
    classify_image_fn: Callable[[Image], ClassificationResult],
    get_runners_fn: Callable[[list[str], Settings], Mapping[str, object]],
    jurisdiction_from_patent_id_fn: Callable[[str], str],
    get_preprocessing_steps_fn: Callable[[str, Settings], list[str]],
    preprocess_fn: Callable[[Image, list[str]], tuple[Image, list[str]]],
    run_cascade_ocsr_fn: Callable[..., Awaitable[OCSRResult]],
) -> PreparedStructureOCSR | None:
    try:
        img_bytes = image_path.read_bytes()
        content_hash = image_hash_fn(img_bytes)
    except OSError:
        return None

    live_rollout = drawing_rollout_state(settings) in LIVE_DRAWING_ROLLOUT_STATES
    if settings.drawing_result_cache_enabled and not live_rollout and content_hash in result_cache:
        logger.debug("ocsr_cache_hit")
        cached = result_cache[content_hash]
        if cached.is_markush:
            governed = _governed_markush_result(cached, settings)
            if governed is None:
                logger.error("markush_ocsr_missing_cxsmiles", tool=cached.tool)
                return None
            return build_markush_prepared_structure(
                patent_id=patent_id,
                page_number=page_number,
                structure_index=structure_index,
                smiles=governed.cxsmiles,
                confidence=governed.confidence,
                extraction_tool=governed.tool,
                input_image_sha256=content_hash,
            )
        governed = apply_resolution_gates(
            cached,
            min_resolved_conf=settings.drawing_cascade_min_resolved_conf,
            max_resolved_atoms=settings.drawing_max_resolved_atoms,
        )
        if not governed.valid or not governed.smiles:
            logger.info("ocsr_cache_entry_abstained", tool=cached.tool)
            return None
        return PreparedStructureOCSR(
            fused=governed,
            input_image_sha256=content_hash,
        )

    if settings.drawing_classifier_enabled:
        try:
            img = bytes_to_image_fn(img_bytes)
            classification = classify_image_fn(img)
            logger.debug(
                "image_classified",
                category=classification.category,
                confidence=classification.confidence,
            )

            if classification.category == ImageCategory.NON_CHEMICAL:
                logger.info("non_chemical_routed_to_ocsr")

            if classification.category == ImageCategory.REACTION:
                logger.info("reaction_routed_to_ocsr")

            if classification.category == ImageCategory.MARKUSH:
                if settings.drawing_markushgrapher_enabled and drawing_specialist_tool_can_emit(
                    settings,
                    "drawing_markush_rollout_state",
                ):
                    logger.info(
                        "markush_detected_routing_to_markushgrapher",
                        rollout_state=getattr(settings, "drawing_markush_rollout_state", ""),
                    )
                    mg_runners = get_runners_fn(["markushgrapher"], settings)
                    mg_runner = mg_runners.get("markushgrapher")
                    if mg_runner:
                        run_markush = getattr(mg_runner, "run", None)
                        predict_markush = getattr(mg_runner, "predict", None)
                        if callable(run_markush):
                            mg_result = await run_markush(image_path)
                        elif callable(predict_markush):
                            mg_result = await predict_markush(image_path)
                        else:
                            mg_result = None
                        governed = (
                            _governed_markush_result(mg_result, settings) if mg_result else None
                        )
                        if governed is not None:
                            return build_markush_prepared_structure(
                                patent_id=patent_id,
                                page_number=page_number,
                                structure_index=structure_index,
                                smiles=governed.cxsmiles,
                                confidence=governed.confidence,
                                extraction_tool=governed.tool,
                                input_image_sha256=content_hash,
                            )
                else:
                    logger.debug(
                        "markush_detected_but_not_live",
                        enabled=settings.drawing_markushgrapher_enabled,
                        rollout_state=getattr(settings, "drawing_markush_rollout_state", ""),
                    )
        except OCSRExecutionError:
            raise
        except (ImportError, ValueError, RuntimeError, OSError) as exc:
            logger.warning(
                "classification_failed",
                error_type=safe_exception_type(exc),
            )

    jurisdiction = jurisdiction_from_patent_id_fn(patent_id)
    prep_steps = get_preprocessing_steps_fn(jurisdiction, settings)
    applied_steps: list[str] = []
    try:
        img = bytes_to_image_fn(img_bytes)
        preprocessed, applied_steps = preprocess_fn(img, prep_steps)
        prep_path = image_path.parent / f"{image_path.stem}_prep.png"
        encoded = BytesIO()
        preprocessed.save(encoded, format="PNG")
        atomic_write_bytes(prep_path, encoded.getvalue())
        ocsr_input = prep_path
    except (ImportError, ValueError, RuntimeError, OSError) as exc:
        logger.warning(
            "preprocessing_failed",
            error_type=safe_exception_type(exc),
        )
        ocsr_input = image_path

    text_formula_signal, text_formula_error = extract_text_formula_signal(patent_text)
    if text_formula_error:
        logger.debug("text_signal_extraction_failed")
    text_smiles_signal = ""
    if getattr(settings, "drawing_text_smiles_enabled", False) and patent_text:
        text_smiles_signal, text_smiles_error = await extract_text_smiles_signal(
            patent_text,
            max_names=getattr(settings, "drawing_text_smiles_max_names", 3),
            max_cas=getattr(settings, "drawing_text_smiles_max_cas", 5),
        )
        if text_smiles_error:
            logger.debug("text_smiles_signal_extraction_failed")

    # Pull dictionary-known abbreviation labels from the patent text and
    # forward them to the cascade so ``ensemble.fuse`` can expand placeholder
    # atoms (`*`, `[U]`, `[*]`) in voter SMILES output.
    abbreviation_labels = extract_abbreviation_labels(patent_text)
    if abbreviation_labels:
        logger.debug(
            "abbreviation_labels_extracted",
            count=len(abbreviation_labels),
        )

    fused = await run_cascade_ocsr_fn(
        ocsr_input,
        all_runners,
        settings,
        text_smiles=text_smiles_signal,
        text_formula=text_formula_signal,
        ocr_labels=abbreviation_labels or None,
    )

    if (
        settings.drawing_result_cache_enabled
        and not live_rollout
        and (fused.valid or (fused.is_markush and bool(fused.cxsmiles)))
    ):
        result_cache[content_hash] = fused

    if fused.is_markush:
        governed = _governed_markush_result(fused, settings)
        if governed is None:
            logger.error("markush_ocsr_missing_cxsmiles", tool=fused.tool)
            return None
        return build_markush_prepared_structure(
            patent_id=patent_id,
            page_number=page_number,
            structure_index=structure_index,
            smiles=governed.cxsmiles,
            confidence=governed.confidence,
            extraction_tool=governed.tool,
            input_image_sha256=content_hash,
        )

    return PreparedStructureOCSR(
        fused=fused,
        applied_steps=applied_steps,
        input_image_sha256=content_hash,
    )


async def finalize_structure_analysis(
    *,
    fused: OCSRResult,
    image_path: Path,
    patent_id: str,
    page_number: int,
    structure_index: int,
    target_smiles: str,
    settings: Settings,
    patent_text: str,
    applied_steps: list[str],
    input_image_sha256: str,
    compute_tanimoto_fn: Callable[[str, str], float],
    check_substructure_fn: Callable[[str, str], bool],
) -> DrawingStructure:
    from praviar_pipeline.ocsr.postprocessing import postprocess

    processed_smiles, post_steps = postprocess(
        fused.smiles,
        steps=["repair_valence", "remove_salts", "canonicalise"],
    )

    text_validated = False
    text_method = ""
    if settings.drawing_text_validation_enabled and patent_text:
        try:
            from praviar_pipeline.ocsr.text_validation import validate_against_text

            text_result = await validate_against_text(
                processed_smiles,
                patent_text,
                tanimoto_threshold=settings.drawing_text_validation_tanimoto_threshold,
            )
            text_validated = text_result.validated
            text_method = text_result.method
            logger.debug(
                "text_validation_result",
                validated=text_validated,
                method=text_method,
            )
        except (
            ImportError,
            httpx.HTTPError,
            ConnectionError,
            TimeoutError,
            ValueError,
            RuntimeError,
        ) as exc:
            logger.warning(
                "text_validation_failed",
                error_type=safe_exception_type(exc),
            )

    tanimoto = compute_tanimoto_fn(processed_smiles, target_smiles)
    is_sub_of_target = check_substructure_fn(processed_smiles, target_smiles)
    target_is_sub = check_substructure_fn(target_smiles, processed_smiles)
    from praviar_pipeline.ocsr.stereo_validation import validate_stereo

    stereo = validate_stereo(
        processed_smiles,
        target_smiles=target_smiles,
        claim_text=patent_text,
    )

    inchi_key = ""
    try:
        from praviar_pipeline.ocsr.postprocessing import to_inchi_key

        inchi_key = to_inchi_key(processed_smiles)
    except (ImportError, ValueError, RuntimeError):
        pass

    return build_final_drawing_structure(
        patent_id=patent_id,
        page_number=page_number,
        structure_index=structure_index,
        raw_smiles=fused.smiles,
        processed_smiles=processed_smiles,
        inchi_key=inchi_key,
        confidence=fused.confidence,
        extraction_tool=fused.tool,
        input_image_sha256=input_image_sha256,
        applied_steps=applied_steps,
        post_steps=post_steps,
        rdkit_valid=fused.valid,
        pubchem_match=text_validated and "pubchem" in text_method,
        tanimoto_to_target=tanimoto,
        is_substructure_of_target=is_sub_of_target,
        target_is_substructure=target_is_sub,
        drawing_risk_signal=compute_risk_level(tanimoto, settings),
        cropped_structure_image=str(image_path),
        stereo_flag=stereo.flag,
        stereo_cip_count=stereo.ocsr_cip_count,
        stereo_ez_count=stereo.ocsr_ez_count,
        stereo_target_cip_count=stereo.target_cip_count,
        stereo_target_ez_count=stereo.target_ez_count,
        stereo_claim_mentions=stereo.claim_mentions_stereo,
        stereo_details=stereo.details,
    )

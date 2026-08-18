"""Confidence-cascade helpers for drawing OCSR."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from praviar_pipeline.models.drawing import OCSRResult
from praviar_pipeline.ocsr.ensemble import apply_resolution_gates, fuse
from praviar_pipeline.ocsr.reranking import score_plausibility

if TYPE_CHECKING:
    from pathlib import Path

    from praviar_pipeline.config import Settings
    from praviar_pipeline.ocsr.runner import OCSRRunner

logger = structlog.get_logger()


async def run_cascade_ocsr(
    image_path: Path,
    all_runners: dict[str, OCSRRunner],
    settings: Settings,
    *,
    text_smiles: str = "",
    text_formula: str = "",
    ocr_labels: list[str] | None = None,
) -> OCSRResult:
    """Run the drawing OCSR confidence cascade.

    ``ocr_labels`` is forwarded to every ``fuse(...)`` call so voter SMILES
    with placeholder atoms (``*``/``[U]``) can be expanded against the merged
    abbreviation dictionary before fusion.
    """
    if not settings.drawing_cascade_enabled:
        results = {}
        for tool, runner in all_runners.items():
            results[tool] = await runner.predict(image_path)
        return fuse(
            results,
            strategy="confidence_cascade",
            confidence_threshold=settings.drawing_confidence_threshold,
            text_smiles=text_smiles or None,
            text_formula=text_formula or None,
            ocr_labels=ocr_labels or None,
        )

    primary = all_runners.get("molscribe")
    if not primary:
        results = {}
        for tool, runner in all_runners.items():
            results[tool] = await runner.predict(image_path)
        return fuse(
            results,
            strategy="confidence_cascade",
            text_smiles=text_smiles or None,
            text_formula=text_formula or None,
            ocr_labels=ocr_labels or None,
        )

    primary_result = await primary.predict(image_path)
    logger.debug(
        "cascade_primary",
        confidence=primary_result.confidence,
        valid=primary_result.valid,
    )

    if (
        primary_result.valid
        and primary_result.smiles
        and primary_result.confidence >= settings.drawing_cascade_high_threshold
    ):
        plausibility = score_plausibility(primary_result.smiles)
        if plausibility >= settings.drawing_cascade_plausibility_threshold:
            logger.info("cascade_accepted_primary", confidence=primary_result.confidence)
            return apply_resolution_gates(
                OCSRResult(
                    smiles=primary_result.smiles,
                    confidence=primary_result.confidence,
                    confidence_available=primary_result.confidence_available,
                    valid=True,
                    tool="cascade:molscribe_high_conf",
                    latency_ms=primary_result.latency_ms,
                ),
                min_resolved_conf=settings.drawing_cascade_min_resolved_conf,
                max_resolved_atoms=settings.drawing_max_resolved_atoms,
            )

    if (
        primary_result.valid
        and primary_result.confidence >= settings.drawing_cascade_medium_threshold
    ):
        escalation_runners = {
            tool: runner for tool, runner in all_runners.items() if tool in {"molsight", "decimer"}
        }
        if escalation_runners:
            results = {"molscribe": primary_result}
            for tool, runner in escalation_runners.items():
                results[tool] = await runner.predict(image_path)

            logger.info("cascade_medium_escalation", models=list(results.keys()))
            return fuse(
                results,
                strategy="confidence_cascade",
                confidence_threshold=settings.drawing_confidence_threshold,
                text_smiles=text_smiles or None,
                text_formula=text_formula or None,
                ocr_labels=ocr_labels or None,
            )

    results = {"molscribe": primary_result}
    for tool, runner in all_runners.items():
        if tool == "molscribe":
            continue
        results[tool] = await runner.predict(image_path)

    logger.info("cascade_full_ensemble", models=list(results.keys()))
    return fuse(
        results,
        strategy="confidence_cascade",
        confidence_threshold=settings.drawing_confidence_threshold,
        text_smiles=text_smiles or None,
        text_formula=text_formula or None,
        ocr_labels=ocr_labels or None,
    )

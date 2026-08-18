"""Post-search enrichment helpers for the Praviar Pipeline runtime."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import structlog

from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()


async def run_post_search_enrichment(
    *,
    completed_step: int,
    patent_hits: list,
    timing_data: list,
    make_timing: Callable[[str, float, int, int], Any],
) -> tuple[list, bool]:
    need_families = completed_step < 4 and bool(patent_hits)

    if not need_families:
        return patent_hits, False

    updated_patent_hits = patent_hits

    from praviar_pipeline.pipeline.step2c_families import expand_and_select_families

    step_start = time.time()
    patents_before_expansion = len(updated_patent_hits)
    updated_patent_hits = await expand_and_select_families(updated_patent_hits)
    timing_data.append(
        make_timing(
            "step2c_families",
            step_start,
            patents_before_expansion,
            len(updated_patent_hits),
        )
    )
    logger.info("step2c_result", patents_after_families=len(updated_patent_hits))

    return updated_patent_hits, True


async def run_post_triage_drawing_enrichment(
    *,
    patent_hits: list,
    compound,
    settings,
    timing_data: list,
    notify: Callable[[int, str, str, dict], None],
    make_timing: Callable[[str, float, int, int], Any],
) -> Any:
    """Run drawing analysis on the post-triage relevant patent set.

    Called after step3 triage so that EPO OPS drawing downloads are bounded to
    the selected relevant-patent set rather than the full search result.
    """
    from praviar_pipeline.models.drawing import DrawingEvidenceStore
    from praviar_pipeline.pipeline.step2d_drawings import analyze_patent_drawings

    notify(2, "drawings", "started", {"description": "Analyzing patent drawings"})
    step_start = time.time()
    drawing_results = await analyze_patent_drawings(
        patent_hits,
        compound.canonical_smiles if compound else "",
        settings,
    )
    timing_data.append(
        make_timing(
            "step2d_drawings",
            step_start,
            len(patent_hits),
            drawing_results.total_structures_extracted,
        )
    )
    logger.info(
        "step2d_result",
        patents_analyzed=drawing_results.total_patents_with_images,
        structures_found=drawing_results.total_structures_extracted,
        high_risk=drawing_results.total_high_risk_structures,
    )
    notify(
        2,
        "drawings",
        "completed",
        {"structures_found": drawing_results.total_structures_extracted},
    )

    evidence = DrawingEvidenceStore(drawing_results)
    logger.info(
        "drawing_evidence_store_built",
        patents=len(evidence),
        patents_with_structures=sum(
            1 for patent_id in evidence.patent_ids if evidence.has_structures(patent_id)
        ),
    )
    return evidence


async def run_claims_enrichment(*, completed_step: int, patent_hits: list) -> None:
    if completed_step >= 6 or not patent_hits:
        return

    from praviar_pipeline.pipeline.step2c_families import (
        enrich_biblio_from_epo_ops,
        enrich_claims_text,
    )

    # Enrich title/abstract for INPADOC stubs concurrently with claims text.
    # Both run before triage (step 5) so the classifier sees real patent text.
    # return_exceptions=True lets both complete independently — enrichment is
    # optional and a single EPO API failure should not cancel the sibling task.
    results = await asyncio.gather(
        enrich_biblio_from_epo_ops(patent_hits),
        enrich_claims_text(patent_hits),
        return_exceptions=True,
    )
    for res in results:
        if isinstance(res, asyncio.CancelledError):
            raise res
    biblio_enriched = results[0] if not isinstance(results[0], BaseException) else 0
    claims_enriched = results[1] if not isinstance(results[1], BaseException) else 0
    for label, exc in [("biblio", results[0]), ("claims", results[1])]:
        if isinstance(exc, BaseException):
            logger.warning(
                "enrichment_partial_failure",
                step=label,
                error_type=safe_exception_type(exc),
            )
    logger.info(
        "step2_6_enrichment",
        biblio_enriched=biblio_enriched,
        claims_enriched=claims_enriched,
        total=len(patent_hits),
    )

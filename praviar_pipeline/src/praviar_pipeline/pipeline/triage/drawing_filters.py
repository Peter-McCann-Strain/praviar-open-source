"""Drawing-based auto-filter helpers for Step 3 triage."""

from __future__ import annotations

from typing import Protocol

import structlog

from praviar_pipeline.models.triage import Relevance, TriageResult

logger = structlog.get_logger()


class TriageDrawingSettings(Protocol):
    triage_drawing_auto_relevant_tanimoto: float
    triage_drawing_auto_relevant_require_substructure: bool
    triage_drawing_auto_not_relevant_tanimoto: float
    triage_drawing_auto_not_relevant_min_structures: int
    triage_drawing_auto_not_relevant_min_confidence: float


def auto_triage_with_drawings(
    patents,
    drawing_evidence,
    *,
    settings: TriageDrawingSettings,
) -> tuple[list[TriageResult], list]:
    """Classify patents using drawing evidence alone, bypassing the LLM."""
    auto_results: list[TriageResult] = []
    remaining = []

    for patent in patents:
        patent_id = patent.patent_id
        highest_tc = drawing_evidence.get_highest_tanimoto(patent_id)
        has_substructure = drawing_evidence.has_substructure_match(patent_id)
        if highest_tc >= settings.triage_drawing_auto_relevant_tanimoto and (
            has_substructure or not settings.triage_drawing_auto_relevant_require_substructure
        ):
            auto_results.append(
                TriageResult(
                    patent_id=patent_id,
                    relevance=Relevance.RELEVANT,
                    reason=(
                        f"Drawing auto-triage: structure with Tanimoto {highest_tc:.2f} to target"
                        f"{' (substructure match)' if has_substructure else ''}"
                    ),
                    confidence=0.90,
                    drawing_auto_filtered=True,
                    drawing_tanimoto=highest_tc,
                )
            )
            logger.info(
                "triage_auto_relevant",
                tanimoto=highest_tc,
                substructure=has_substructure,
            )
            continue

        # Negative drawing similarity is never exclusionary: OCSR can miss the
        # relevant embodiment, claims can be broader than depicted structures,
        # and drawings are not a complete claim record. Preserve the patent for
        # the ordinary evidence-aware triage path.
        remaining.append(patent)

    logger.info(
        "triage_auto_filter_summary",
        auto_relevant=sum(1 for result in auto_results if result.relevance == Relevance.RELEVANT),
        auto_not_relevant=sum(
            1 for result in auto_results if result.relevance == Relevance.NOT_RELEVANT
        ),
        remaining_for_llm=len(remaining),
    )

    return auto_results, remaining

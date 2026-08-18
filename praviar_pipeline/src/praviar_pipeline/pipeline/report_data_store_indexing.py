"""Index helpers for :mod:`praviar_pipeline.pipeline.report_data_store`."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praviar_pipeline.models.analysis import PatentAnalysis
    from praviar_pipeline.models.equivalents import DoEAssessment
    from praviar_pipeline.models.invalidity import InvalidityAssessment
    from praviar_pipeline.models.patent import PatentHit


def index_analyses(analyses: list[PatentAnalysis]) -> dict[str, PatentAnalysis]:
    return {analysis.patent_id: analysis for analysis in analyses}


def index_doe_assessments(
    doe_assessments: list[DoEAssessment],
) -> dict[str, list[DoEAssessment]]:
    indexed: dict[str, list[DoEAssessment]] = defaultdict(list)
    for assessment in doe_assessments:
        indexed[assessment.patent_id].append(assessment)
    return dict(indexed)


def index_invalidity_assessments(
    invalidity_assessments: list[InvalidityAssessment],
) -> dict[str, InvalidityAssessment]:
    return {assessment.patent_id: assessment for assessment in invalidity_assessments}


def index_patent_details(
    patent_hits: list[PatentHit] | None,
    analyzed_ids: set[str],
) -> dict[str, dict]:
    details: dict[str, dict] = {}
    if patent_hits:
        for patent_hit in patent_hits:
            if patent_hit.patent_id in analyzed_ids and hasattr(patent_hit, "model_dump"):
                details[patent_hit.patent_id] = patent_hit.model_dump(mode="json")
    return details

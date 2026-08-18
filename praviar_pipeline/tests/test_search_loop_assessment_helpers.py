from __future__ import annotations

from unittest.mock import MagicMock

from praviar_pipeline.models.patent import PatentHit, PatentSource
from praviar_pipeline.models.report import SourceHealth
from praviar_pipeline.models.report_common import SourceHealthEntry, SourceStatus
from praviar_pipeline.models.report_evidence import (
    EvidenceCollectionDirective,
    EvidenceDirectivePriority,
)
from praviar_pipeline.models.search import ExpandedSearchQueries
from praviar_pipeline.models.triage import Relevance, TriageResult
from praviar_pipeline.pipeline.search_loop import (
    build_search_gap_plan,
    synthesize_search_queries_from_directives,
)


def test_build_search_gap_plan_falls_back_to_all_hits_without_material_triage() -> None:
    settings = MagicMock()
    settings.required_record_components = []
    settings.clearance_threshold_profile = "world_class_us_ep"

    patent_hits = [
        PatentHit(
            patent_id="US1234567B2",
            jurisdiction="US",
            claims_text="",
            sources=[PatentSource.PUBCHEM],
            application_number="",
            transactions=[],
        )
    ]
    triage = [
        TriageResult(
            patent_id="US1234567B2",
            relevance=Relevance.NOT_RELEVANT,
            reason="Later ruled out.",
        )
    ]
    source_health = SourceHealth(
        entries=[SourceHealthEntry(source="patentsview", status=SourceStatus.FAILED)]
    )

    gap_plan = build_search_gap_plan(
        patent_hits,
        triage,
        source_health,
        settings=settings,
    )

    assert [hit.patent_id for hit in gap_plan.scoped_hits] == ["US1234567B2"]
    assert gap_plan.patents_missing_claims == ["US1234567B2"]


def test_synthesize_search_queries_from_directives_returns_none_for_non_searchable_types() -> None:
    directives = [
        EvidenceCollectionDirective(
            directive_id="collect_us_file_wrapper_dossier:US1234567B2",
            directive_type="collect_us_file_wrapper_dossier",
            priority=EvidenceDirectivePriority.CRITICAL,
            target_patent_ids=["US1234567B2"],
            recommended_adapters=["uspto_odp"],
            summary="Collect dossier history.",
            rationale="Needed before clear.",
        )
    ]
    accumulated = ExpandedSearchQueries(patent_synonyms=["aspirin"])

    synthesized = synthesize_search_queries_from_directives(
        directives,
        [PatentHit(patent_id="US1234567B2", assignees=["Example"], cpc_codes=["A61K31/00"])],
        accumulated,
    )

    assert synthesized is None

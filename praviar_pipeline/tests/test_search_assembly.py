from __future__ import annotations

from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.pipeline.search.models import PreparedRankingInputs, SearchExecutionSummary
from praviar_pipeline.pipeline.search.orchestration import assemble_prepared_search_results


def test_assemble_prepared_search_results_builds_hits_and_contribution_summary() -> None:
    summary = SearchExecutionSummary(
        sdq_results=[{"publicationnumber": "US100"}],
        source_timings={"pubchem_sdq": 5},
    )
    fake_hit = type("Hit", (), {"patent_id": "US100", "sources": [PatentSource.PUBCHEM]})()
    contribution_summary = type(
        "ContributionSummary",
        (),
        {
            "total_unique_patents": 1,
            "sdq_total": 1,
            "source_metrics": {"pubchem_sdq": {"total": 1}},
        },
    )()

    prepared = assemble_prepared_search_results(
        summary=summary,
        ranked_inputs=PreparedRankingInputs(
            source_map={"US100": {PatentSource.PUBCHEM}},
            multi_source_ids={"US100"},
            ranked_sdq=[{"publicationnumber": "US100"}],
        ),
        assemble_hits_fn=lambda **kwargs: ([fake_hit], {"US100"}),
        build_search_contribution_summary_fn=lambda **kwargs: contribution_summary,
        normalize_patent_id=lambda patent_id: patent_id,
    )

    assert prepared.source_map == {"US100": {PatentSource.PUBCHEM}}
    assert prepared.multi_source_ids == {"US100"}
    assert prepared.ranked_sdq == [{"publicationnumber": "US100"}]
    assert prepared.hits == [fake_hit]
    assert prepared.seen_norm_ids == {"US100"}
    assert prepared.contribution_summary is contribution_summary

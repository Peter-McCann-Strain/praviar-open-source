from __future__ import annotations

from praviar_pipeline.models.patent import PatentSource
from praviar_pipeline.pipeline.search.models import SearchExecutionSummary
from praviar_pipeline.pipeline.search.orchestration import prepare_ranked_search_inputs


def test_prepare_ranked_search_inputs_builds_source_map_and_ranking_inputs() -> None:
    summary = SearchExecutionSummary(
        sdq_results=[{"publicationnumber": "US100"}],
        surechembl_results=[("US100", PatentSource.SURECHEMBL)],
    )
    captured: dict[str, object] = {}
    settings = type(
        "Settings",
        (),
        {"search_max_ranked_results": 25, "collect_audit_trail": True},
    )()

    def fake_rank_patents(sdq_results, compound, **kwargs):
        captured["multi_source_ids"] = kwargs["multi_source_ids"]
        captured["max_results"] = kwargs["max_results"]
        captured["collect_audit"] = kwargs["collect_audit"]
        return [{"publicationnumber": "US100"}]

    prepared = prepare_ranked_search_inputs(
        summary=summary,
        compound=object(),
        settings=settings,
        build_source_map_fn=lambda **kwargs: {
            "US100": {PatentSource.PUBCHEM, PatentSource.SURECHEMBL}
        },
        rank_patents_fn=fake_rank_patents,
    )

    assert prepared.source_map == {"US100": {PatentSource.PUBCHEM, PatentSource.SURECHEMBL}}
    assert prepared.multi_source_ids == {"US100"}
    assert prepared.ranked_sdq == [{"publicationnumber": "US100"}]
    assert captured == {
        "multi_source_ids": {"US100"},
        "max_results": 25,
        "collect_audit": True,
    }

from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.checkpoint import (
    CheckpointIntegrityKeyRing,
    build_checkpoint,
    load_latest_checkpoint,
)
from praviar_pipeline.pipeline.runtime.reanalysis import (
    merge_reanalysis_results,
    select_failed_patents,
    write_reanalysis_checkpoint,
)

TEST_INTEGRITY_KEYS = CheckpointIntegrityKeyRing(
    active_key_id="test-v1",
    _keys={"test-v1": b"test-pipeline-checkpoint-hmac-key-00000001"},
)


def test_select_failed_patents_filters_patent_hits():
    patent_hits = [
        SimpleNamespace(patent_id="US123"),
        SimpleNamespace(patent_id="US456"),
    ]
    analysis_failures = [
        SimpleNamespace(patent_id="US456"),
    ]

    failed_ids, retry_patents = select_failed_patents(patent_hits, analysis_failures)

    assert failed_ids == {"US456"}
    assert [patent.patent_id for patent in retry_patents] == ["US456"]


def test_merge_reanalysis_results_keeps_unresolved_failures():
    existing_analyses = [SimpleNamespace(patent_id="US111")]
    existing_failures = [SimpleNamespace(patent_id="US222"), SimpleNamespace(patent_id="US333")]
    new_analyses = [SimpleNamespace(patent_id="US222")]
    new_failures = [SimpleNamespace(patent_id="US444")]

    merged_analyses, merged_failures = merge_reanalysis_results(
        existing_analyses,
        existing_failures,
        new_analyses,
        new_failures,
    )

    assert [analysis.patent_id for analysis in merged_analyses] == ["US111", "US222"]
    assert [failure.patent_id for failure in merged_failures] == ["US333", "US444"]


def test_write_reanalysis_checkpoint_preserves_drawing_results(tmp_path):
    class DummyDrawingResults:
        def to_dict(self) -> dict:
            return {"patents": {"US123": {"structures": 1}}}

    checkpoint = build_checkpoint(
        run_id="reanalysis-test",
        completed_step=5,
        compound_input="aspirin",
    )

    write_reanalysis_checkpoint(
        checkpoint_dir_path=str(tmp_path),
        checkpoint=checkpoint,
        state={
            "compound": {"name": "aspirin"},
            "expanded_queries": {"cpc_codes": []},
            "source_health": {"entries": []},
            "search_funnel": [],
            "drawing_results": DummyDrawingResults(),
            "all_triage_results": [],
            "triage_input_tokens": 10,
            "triage_output_tokens": 3,
            "triage_failed": 0,
            "reasoning_traces": [],
            "timing_data": [],
        },
        patent_hits=[],
        triage_results=[],
        merged_analyses=[],
        merged_failures=[],
        integrity_keys=TEST_INTEGRITY_KEYS,
    )

    saved = load_latest_checkpoint(tmp_path, integrity_keys=TEST_INTEGRITY_KEYS)

    assert saved is not None
    assert saved.completed_step == 8
    assert saved.drawing_results == {"patents": {"US123": {"structures": 1}}}

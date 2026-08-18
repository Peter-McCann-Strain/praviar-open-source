from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.pipeline.runtime.decisioning_outputs import (
    build_decisioning_evidence_substrate,
)


def test_build_decisioning_evidence_substrate_passes_settings_to_collection_plan():
    settings = SimpleNamespace(asset_type_hint="small_molecule")
    received: dict[str, object] = {}

    def fake_build_evidence_collection_plan_fn(**kwargs):
        received["settings"] = kwargs["settings"]
        return []

    substrate = build_decisioning_evidence_substrate(
        report=SimpleNamespace(coverage_gaps=[]),
        coverage_context=SimpleNamespace(),
        matter_evidence_index=SimpleNamespace(),
        record_completeness=SimpleNamespace(),
        claim_program_summary=SimpleNamespace(),
        claim_program_decisions=[],
        settings=settings,
        matter_graph=SimpleNamespace(),
        matter_graph_summary=SimpleNamespace(),
        build_coverage_gaps_fn=lambda **_: [],
        build_authority_coverage_fn=lambda **_: SimpleNamespace(),
        reuse_or_build_evidence_artifacts_fn=lambda **_: [],
        reuse_or_build_evidence_adapter_results_fn=lambda **_: [],
        build_evidence_collection_plan_fn=fake_build_evidence_collection_plan_fn,
        reuse_or_build_collector_runs_fn=lambda **_: [],
        build_run_observability_fn=lambda **_: SimpleNamespace(),
        reuse_or_build_matter_store_fn=lambda **_: SimpleNamespace(),
        build_evidence_artifacts=lambda **_: [],
        build_evidence_adapter_results=lambda **_: [],
    )

    assert received["settings"] is settings
    assert substrate.evidence_collection_plan == []

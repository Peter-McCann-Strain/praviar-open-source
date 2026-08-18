from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.pipeline.runtime.decisioning_outputs import (
    build_evidence_collection_plan,
)


def _claim_only_coverage_context(*, patent_ids: list[str]):
    return SimpleNamespace(
        coverage_summary=SimpleNamespace(
            patents_missing_claims=patent_ids,
        )
    )


def _empty_claim_program_summary():
    return SimpleNamespace(
        contested_claim_ids=[],
        contested_patent_ids=[],
        medium_risk_claim_ids=[],
        medium_risk_patent_ids=[],
    )


def test_build_evidence_collection_plan_filters_uncertified_claim_collectors():
    directives = build_evidence_collection_plan(
        record_completeness=SimpleNamespace(missing_components=["claims_text"]),
        coverage_context=_claim_only_coverage_context(patent_ids=["US1234567B2", "EP1234567B1"]),
        evidence_adapter_results=[],
        claim_program_summary=_empty_claim_program_summary(),
        settings=SimpleNamespace(
            asset_type_hint="markush_candidate",
            matter_type="small_molecule",
        ),
    )

    assert len(directives) == 1
    assert directives[0].directive_type == "collect_claims_text"
    assert directives[0].recommended_adapters == []


def test_build_evidence_collection_plan_keeps_certified_claim_collectors():
    directives = build_evidence_collection_plan(
        record_completeness=SimpleNamespace(missing_components=["claims_text"]),
        coverage_context=_claim_only_coverage_context(patent_ids=["US1234567B2", "EP1234567B1"]),
        evidence_adapter_results=[],
        claim_program_summary=_empty_claim_program_summary(),
        settings=SimpleNamespace(
            asset_type_hint="small_molecule",
            matter_type="small_molecule",
        ),
    )

    assert len(directives) == 1
    assert directives[0].recommended_adapters == [
        "patentsview",
        "bigquery",
        "epo_search",
    ]


def test_build_evidence_collection_plan_filters_authoritative_adapters_by_jurisdiction():
    directives = build_evidence_collection_plan(
        record_completeness=SimpleNamespace(missing_components=["authoritative_records"]),
        coverage_context=SimpleNamespace(
            coverage_summary=SimpleNamespace(
                patents_missing_authoritative_records=["EP1234567B1"],
            )
        ),
        evidence_adapter_results=[],
        claim_program_summary=_empty_claim_program_summary(),
        settings=SimpleNamespace(
            asset_type_hint="small_molecule",
            matter_type="small_molecule",
        ),
    )

    assert len(directives) == 1
    assert directives[0].directive_type == "collect_authoritative_records"
    assert directives[0].recommended_adapters == ["epo_search", "epo_register"]

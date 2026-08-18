from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.report import (
    CollectionAttempt,
    EvidenceAdapterKind,
    EvidenceAuthorityTier,
    EvidenceCollectionState,
    EvidenceCollectorDefinition,
    EvidenceCollectorRun,
)
from praviar_pipeline.models.report_common import SourceStatus
from praviar_pipeline.pipeline.runtime import evidence_collectors as attempts_module
from praviar_pipeline.pipeline.runtime.evidence_collectors import (
    build_evidence_collector_runs,
    merge_evidence_collector_runs,
    record_live_collector_attempts,
)


def _adapter_result(**overrides):
    base = dict(
        adapter_name="patentsview",
        adapter_kind=EvidenceAdapterKind.SEARCH,
        authority_tier=EvidenceAuthorityTier.SUPPORTING,
        supports_authoritative_findings=False,
        expected_components=["claims_text"],
        collection_state=EvidenceCollectionState.COLLECTED,
        required_before_clear=False,
        covered_patent_ids=["US123"],
        missing_patent_ids=[],
        covered_components=["claims_text"],
        missing_components=[],
        freshness_note="fresh",
        status=SourceStatus.OK,
        artifact_count=1,
        warnings=[],
        artifacts=[SimpleNamespace(patent_id="US123")],
        target_patent_ids=[],
        retry_after_seconds=None,
        rate_limit_remaining=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_evidence_collector_runs_derives_targets_and_attempt_summary() -> None:
    result = _adapter_result(
        covered_patent_ids=[],
        missing_patent_ids=["US123"],
        collection_state=EvidenceCollectionState.MISSING,
        status=SourceStatus.SKIPPED,
    )
    directives = [
        SimpleNamespace(
            directive_id="collect-1",
            recommended_adapters=["patentsview"],
            target_patent_ids=["US123"],
        )
    ]

    runs = build_evidence_collector_runs(
        evidence_adapter_results=[result],
        evidence_collection_plan=directives,
    )

    run = runs[0]
    assert run.target_patent_ids == ["US123"]
    assert run.triggered_directive_ids == ["collect-1"]
    assert run.collection_targets[0].jurisdiction == "US"
    assert run.attempts[0].summary == "Collector has not yet satisfied all required targets."


def test_merge_evidence_collector_runs_preserves_attempts_and_directives() -> None:
    existing = EvidenceCollectorRun(
        definition=EvidenceCollectorDefinition(
            collector_name="patentsview",
            adapter_kind=EvidenceAdapterKind.SEARCH,
            authority_tier=EvidenceAuthorityTier.SUPPORTING,
        ),
        attempts=[
            CollectionAttempt(
                attempt_number=1,
                status=SourceStatus.OK,
                collection_state=EvidenceCollectionState.COLLECTED,
                artifact_count=1,
                summary="old",
            )
        ],
        triggered_directive_ids=["existing"],
    )
    latest = EvidenceCollectorRun(
        definition=EvidenceCollectorDefinition(
            collector_name="patentsview",
            adapter_kind=EvidenceAdapterKind.SEARCH,
            authority_tier=EvidenceAuthorityTier.SUPPORTING,
        ),
        triggered_directive_ids=["latest"],
        attempts=[],
    )

    merged = merge_evidence_collector_runs(
        existing_collector_runs=[existing],
        latest_collector_runs=[latest],
    )

    assert merged[0].attempts[0].summary == "old"
    assert merged[0].triggered_directive_ids == ["existing", "latest"]


def test_record_live_collector_attempts_updates_existing_run() -> None:
    existing = EvidenceCollectorRun(
        definition=EvidenceCollectorDefinition(
            collector_name="patentsview",
            adapter_kind=EvidenceAdapterKind.SEARCH,
            authority_tier=EvidenceAuthorityTier.SUPPORTING,
            expected_components=["claims_text"],
        ),
        expected_components=["claims_text"],
        attempts=[],
    )

    runs = record_live_collector_attempts(
        collector_runs=[existing],
        evidence_collection_plan=[],
        attempt_records=[
            SimpleNamespace(
                collector_name="patentsview",
                status=SourceStatus.OK,
                target_patent_ids=["US123"],
                covered_patent_ids=["US123"],
                missing_patent_ids=[],
                patent_count=1,
                summary="covered",
            )
        ],
    )

    run = runs[0]
    assert run.covered_patent_ids == ["US123"]
    assert run.collection_state == EvidenceCollectionState.COLLECTED
    assert run.attempts[0].summary == "covered"


def test_record_live_collector_attempts_creates_new_run(monkeypatch) -> None:
    monkeypatch.setattr(
        attempts_module,
        "adapter_definition_for",
        lambda _name: SimpleNamespace(
            adapter_name="epo_register",
            adapter_kind=EvidenceAdapterKind.SEARCH,
            default_authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
            supports_authoritative_findings=True,
            expected_components=["ep_register_context"],
            freshness_note="fresh",
        ),
    )

    runs = record_live_collector_attempts(
        collector_runs=[],
        evidence_collection_plan=[
            SimpleNamespace(
                directive_id="collect-ep",
                recommended_adapters=["epo_register"],
                target_patent_ids=["EP123"],
            )
        ],
        attempt_records=[
            SimpleNamespace(
                collector_name="epo_register",
                status=SourceStatus.SKIPPED,
                target_patent_ids=["EP123"],
                covered_patent_ids=[],
                missing_patent_ids=["EP123"],
                patent_count=0,
                summary="missing",
                required_before_clear=True,
            )
        ],
    )

    run = runs[0]
    assert run.definition.collector_name == "epo_register"
    assert run.triggered_directive_ids == ["collect-ep"]
    assert run.collection_state == EvidenceCollectionState.MISSING
    assert run.collection_targets[0].missing_components == ["ep_register_context"]

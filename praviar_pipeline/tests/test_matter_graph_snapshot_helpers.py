from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.analysis import PatentAnalysis, RiskLevel
from praviar_pipeline.models.compound import ResolvedCompound
from praviar_pipeline.models.patent import (
    PatentFamily,
    PatentFamilyMember,
    PatentHit,
    PatentSource,
)
from praviar_pipeline.models.report import SourceHealth
from praviar_pipeline.models.report_common import SourceHealthEntry, SourceStatus
from praviar_pipeline.pipeline.runtime.matter_graph_snapshot import (
    assemble_runtime_evidence_snapshot,
    prepare_runtime_snapshot_inputs,
)


def _compound() -> ResolvedCompound:
    return ResolvedCompound(name="aspirin", original_input="aspirin", input_type="name")


def _analysis() -> PatentAnalysis:
    return PatentAnalysis(
        patent_id="US1234567B2",
        title="Test patent",
        risk_level=RiskLevel.MEDIUM,
        risk_summary="summary",
    )


def _hit() -> PatentHit:
    return PatentHit(
        patent_id="US1234567B2",
        jurisdiction="US",
        application_number="US10/000001",
        claims_text="Claim 1. Example text.",
        sources=[PatentSource.PATENTSVIEW],
        family=PatentFamily(
            family_id="fam-1",
            members=[PatentFamilyMember(country="US", doc_number="1234567", kind="B2")],
        ),
    )


def _settings():
    return SimpleNamespace(
        required_record_components=["claims_text", "family_context", "us_file_wrapper_dossier"],
        clearance_threshold_profile="world_class_us_ep",
        matter_type="small_molecule",
        jurisdiction_policy="us_ep_core",
        source_authority_policy="official_plus_licensed",
    )


def test_prepare_runtime_snapshot_inputs_builds_record_completeness() -> None:
    prepared = prepare_runtime_snapshot_inputs(
        compound=_compound(),
        analyses=[_analysis()],
        doe_assessments=[],
        invalidity_assessments=[],
        analysis_failures=[],
        patent_hits=[_hit()],
        prosecution_cache={},
        source_health=SourceHealth(
            entries=[
                SourceHealthEntry(
                    source="patentsview",
                    status=SourceStatus.OK,
                    patent_count=1,
                    error_message="",
                )
            ]
        ),
        settings=_settings(),
    )

    assert prepared.record_completeness is not None
    assert "us_file_wrapper_dossier" in prepared.record_completeness.required_components
    assert prepared.detail_map["US1234567B2"].claims_text == "Claim 1. Example text."
    assert prepared.prosecution_dossiers == []


def test_assemble_runtime_evidence_snapshot_merges_existing_collector_runs() -> None:
    prepared = prepare_runtime_snapshot_inputs(
        compound=_compound(),
        analyses=[_analysis()],
        doe_assessments=[],
        invalidity_assessments=[],
        analysis_failures=[],
        patent_hits=[_hit()],
        prosecution_cache={},
        source_health=SourceHealth(entries=[]),
        settings=_settings(),
    )

    snapshot = assemble_runtime_evidence_snapshot(
        compound=_compound(),
        analyses=[_analysis()],
        patent_hits=[_hit()],
        prosecution_cache={},
        settings=_settings(),
        existing_collector_runs=[
            SimpleNamespace(
                definition=SimpleNamespace(collector_name="patentsview"),
                attempts=[SimpleNamespace(summary="legacy attempt")],
                triggered_directive_ids=["legacy-directive"],
            )
        ],
        prepared=prepared,
    )

    collector_runs = {run.definition.collector_name: run for run in snapshot.collector_runs}
    assert collector_runs["patentsview"].attempts[0].summary == "legacy attempt"
    assert "legacy-directive" in collector_runs["patentsview"].triggered_directive_ids
    assert snapshot.matter_store.matter_graph_summary.node_count >= 1

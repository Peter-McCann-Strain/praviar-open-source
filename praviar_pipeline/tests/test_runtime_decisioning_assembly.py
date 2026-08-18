from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from praviar_pipeline.models.report import (
    AuthorityCoverage,
    ClaimProgramDecision,
    ClearanceDecisionAudit,
    ClearanceOutcome,
    EvidenceAdapterResult,
    EvidenceArtifact,
    EvidenceArtifactType,
    EvidenceCollectorDefinition,
    EvidenceCollectorRun,
    MatterEdge,
    MatterEdgeType,
    MatterEvidenceIndex,
    MatterGraph,
    MatterGraphSummary,
    MatterNode,
    MatterNodeType,
    MatterStore,
    RecordCompleteness,
    RunObservability,
)
from praviar_pipeline.pipeline.runtime.decisioning_outputs import (
    _reuse_or_build_collector_runs,
    _reuse_or_build_evidence_adapter_results,
    _reuse_or_build_evidence_artifacts,
    _reuse_or_build_matter_graph,
    _reuse_or_build_matter_graph_summary,
    _reuse_or_build_matter_store,
    assemble_clearance_outputs,
)


def test_reuse_helpers_refresh_matter_store_from_current_canonical_state() -> None:
    evidence_artifact = EvidenceArtifact(
        artifact_id="artifact:test",
        artifact_type=EvidenceArtifactType.SEARCH_HIT,
    )
    collector_run = EvidenceCollectorRun(
        definition=EvidenceCollectorDefinition(collector_name="test_adapter")
    )
    report = SimpleNamespace(
        matter_graph=MatterGraph(
            nodes=[
                MatterNode(
                    node_id="compound:aspirin",
                    node_type=MatterNodeType.COMPOUND_VARIANT,
                    label="aspirin",
                )
            ],
            edges=[
                MatterEdge(
                    edge_type=MatterEdgeType.ROOTS,
                    from_node_id="compound:aspirin",
                    to_node_id="patent:US1234567B2",
                )
            ],
        ),
        matter_graph_summary=MatterGraphSummary(
            root_compound="aspirin",
            node_count=1,
            edge_count=1,
        ),
        evidence_artifacts=[evidence_artifact],
        evidence_adapter_results=[EvidenceAdapterResult(adapter_name="test_adapter")],
        collector_runs=[collector_run],
        matter_store=MatterStore(
            matter_graph=MatterGraph(
                nodes=[
                    MatterNode(
                        node_id="compound:aspirin",
                        node_type=MatterNodeType.COMPOUND_VARIANT,
                        label="aspirin",
                    )
                ],
                edges=[],
            )
        ),
        patent_analyses=[SimpleNamespace(patent_id="US1234567B2")],
        compound=SimpleNamespace(name="aspirin"),
    )
    builder = Mock(side_effect=AssertionError("should not be called"))

    matter_graph = _reuse_or_build_matter_graph(
        report=report,
        matter_evidence_index=MatterEvidenceIndex(),
        claim_program_decisions=[],
        patent_hits=[],
        analyses=report.patent_analyses,
        build_matter_graph=builder,
    )
    matter_graph_summary = _reuse_or_build_matter_graph_summary(
        report=report,
        matter_graph=report.matter_graph,
        build_summarize_matter_graph=builder,
    )
    evidence_artifacts = _reuse_or_build_evidence_artifacts(
        report=report,
        matter_evidence_index=MatterEvidenceIndex(),
        claim_program_decisions=[],
        coverage_gaps=[],
        build_evidence_artifacts=builder,
    )
    evidence_adapter_results = _reuse_or_build_evidence_adapter_results(
        report=report,
        matter_evidence_index=SimpleNamespace(),
        evidence_artifacts=evidence_artifacts,
        record_completeness=RecordCompleteness(),
        build_evidence_adapter_results=builder,
    )
    collector_runs = _reuse_or_build_collector_runs(
        report=report,
        evidence_adapter_results=evidence_adapter_results,
        evidence_collection_plan=[],
    )
    matter_store = _reuse_or_build_matter_store(
        report=report,
        matter_graph=report.matter_graph,
        matter_graph_summary=report.matter_graph_summary,
        matter_evidence_index=MatterEvidenceIndex(),
        claim_program_summary=SimpleNamespace(),
        claim_program_decisions=[],
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        collector_runs=collector_runs,
        evidence_collection_plan=[],
        coverage_gaps=[],
        authority_coverage=AuthorityCoverage(),
        record_completeness=RecordCompleteness(),
        run_observability=RunObservability(),
    )

    assert matter_graph is report.matter_graph
    assert matter_graph_summary is report.matter_graph_summary
    assert evidence_artifacts == report.evidence_artifacts
    assert evidence_adapter_results == report.evidence_adapter_results
    assert collector_runs == report.collector_runs
    assert matter_store is not report.matter_store
    assert matter_store.matter_graph is report.matter_graph
    builder.assert_not_called()


def test_assemble_clearance_outputs_keeps_public_payload_shape() -> None:
    report = SimpleNamespace(
        patent_analyses=[SimpleNamespace(patent_id="US1234567B2")],
        compound=SimpleNamespace(name="aspirin"),
        coverage_gaps=["gap"],
        prosecution_dossiers=[],
        analysis_failures=[],
        critic_report=None,
        source_health=SimpleNamespace(failed_sources=[]),
        data_limitations=[],
        search_loop_result=None,
        evidence_artifacts=[],
        evidence_adapter_results=[EvidenceAdapterResult(adapter_name="test_adapter")],
        collector_runs=[],
        matter_graph=MatterGraph(
            nodes=[
                MatterNode(
                    node_id="compound:aspirin",
                    node_type=MatterNodeType.COMPOUND_VARIANT,
                    label="aspirin",
                )
            ],
            edges=[
                MatterEdge(
                    edge_type=MatterEdgeType.ROOTS,
                    from_node_id="compound:aspirin",
                    to_node_id="patent:US1234567B2",
                )
            ],
        ),
        matter_graph_summary=MatterGraphSummary(
            root_compound="aspirin",
            node_count=1,
            edge_count=1,
        ),
    )
    report.matter_store = MatterStore(matter_graph=report.matter_graph)
    coverage_context = SimpleNamespace(
        jurisdiction_patents={"US": ["US1234567B2"], "EP": []},
        blocking_by_jurisdiction={"US": [], "EP": []},
        prosecution_findings=["finding"],
        future_risk=["risk"],
        queried_sources=1,
        ok_sources=1,
        material_patent_count=1,
        patents_with_claims=1,
        patents_with_family=1,
        us_patents_with_file_wrapper_dossier=1,
        us_patents=1,
        ep_patents_with_register_context=0,
        ep_patents=0,
    )
    coverage_context.coverage_summary = SimpleNamespace(
        patents_missing_claim_level_analysis=[],
        patents_missing_authoritative_records=[],
        patents_missing_claims=[],
        patents_missing_family_context=[],
        us_patents_missing_prosecution_context=[],
        us_patents_missing_file_wrapper_dossier=[],
        ep_patents_missing_register_context=[],
        verified_patent_ids=[],
        verification_gaps=[],
        reviewed_patent_ids=["US1234567B2"],
        failed_source_names=[],
        authoritative_source_names=[],
        supporting_source_names=[],
    )
    matter_evidence_index = MatterEvidenceIndex(
        authoritative_source_names=[],
        supporting_source_names=[],
        patent_records=[],
        clearance_grade_ready_patent_ids=["US1234567B2"],
        incomplete_patent_ids=[],
        clearance_grade_ready_family_ids=[],
        incomplete_family_ids=[],
    )
    record_completeness = RecordCompleteness(blocking_gaps=[])
    authority_coverage = AuthorityCoverage()
    run_observability = RunObservability()
    claim_program_decisions = [
        ClaimProgramDecision(
            patent_id="US1234567B2",
            jurisdiction="US",
            claim_number=1,
            evidence_sufficient=True,
        )
    ]
    claim_program_summary = SimpleNamespace(
        blocking_patent_ids=[],
        total_claim_programs_reviewed=1,
        blocking_claim_ids=[],
        contested_claim_ids=[],
        medium_risk_claim_ids=[],
        contested_patent_ids=[],
        medium_risk_patent_ids=[],
        claims_with_insufficient_evidence=[],
    )
    decision = ClearanceOutcome.CLEAR
    decision_audit = ClearanceDecisionAudit()
    jurisdiction_decisions = [SimpleNamespace(jurisdiction="US")]
    decisive_references = [SimpleNamespace(signal="ok")]

    with (
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_coverage_gaps",
            return_value=["gap"],
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_authority_coverage",
            return_value=authority_coverage,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_evidence_collection_plan",
            return_value=[],
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_run_observability",
            return_value=run_observability,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_decision_audit_record",
            return_value=decision_audit,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_jurisdiction_decisions",
            return_value=jurisdiction_decisions,
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_claim_construction_record",
            return_value=SimpleNamespace(record="claim"),
        ),
        patch(
            "praviar_pipeline.pipeline.runtime.decisioning_outputs.build_commercial_exposure",
            return_value=SimpleNamespace(exposure="commercial"),
        ),
    ):
        outputs = assemble_clearance_outputs(
            report=report,
            patent_hits=[SimpleNamespace(patent_id="US1234567B2")],
            matter_evidence_index=matter_evidence_index,
            coverage_context=coverage_context,
            record_completeness=record_completeness,
            claim_program_decisions=claim_program_decisions,
            claim_program_summary=claim_program_summary,
            evidence_quality=0.9,
            warnings=["warning"],
            insufficiency_reasons=[],
            evidence_sufficient_for_clearance=True,
            decision=decision,
            decision_confidence=0.88,
            decision_reasoning=["reason"],
            decisive_references=decisive_references,
            blocking_patent_ids=[],
            jurisdiction_gate_failures={"US": [], "EP": []},
            decision_scope=SimpleNamespace(scope="decision"),
            supporting_scope=SimpleNamespace(scope="support"),
            certification_scope=SimpleNamespace(scope="certification"),
            cohort_status=SimpleNamespace(status="ready"),
            settings=None,
            build_matter_graph=Mock(return_value=report.matter_graph),
            summarize_matter_graph=Mock(return_value=report.matter_graph_summary),
            build_evidence_artifacts=Mock(return_value=report.evidence_artifacts),
            build_evidence_adapter_results=Mock(return_value=report.evidence_adapter_results),
        )

    assert outputs["clearance_decision"].decision is decision
    assert outputs["matter_graph"] is report.matter_graph
    assert outputs["matter_graph_summary"] is report.matter_graph_summary
    assert outputs["coverage_gaps"] == ["gap"]
    assert outputs["authority_coverage"] is authority_coverage
    assert [run.definition.collector_name for run in outputs["collector_runs"]] == ["test_adapter"]
    assert outputs["evidence_collection_plan"] == []
    assert outputs["matter_store"].matter_graph is report.matter_graph
    assert outputs["run_observability"] is run_observability
    assert outputs["clearance_decision"].decision_audit is decision_audit
    assert outputs["jurisdiction_decisions"] == jurisdiction_decisions
    assert outputs["claim_construction_record"].record == "claim"
    assert outputs["commercial_exposure"].exposure == "commercial"

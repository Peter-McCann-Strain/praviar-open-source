from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.patent import (
    PatentFamily,
    PatentFamilyMember,
    PatentHit,
    PatentSource,
    PTABProceeding,
)
from praviar_pipeline.models.report import (
    CollectionAttempt,
    EvidenceArtifact,
    EvidenceArtifactType,
    EvidenceAuthorityTier,
    EvidenceCollectorDefinition,
    EvidenceCollectorRun,
    MatterEdge,
    MatterEdgeType,
    MatterGraph,
    MatterNode,
    MatterNodeType,
    SourceHealth,
)
from praviar_pipeline.models.report_common import SourceHealthEntry, SourceStatus
from praviar_pipeline.models.report_evidence_artifacts import (
    EvidenceAdapterKind,
    EvidenceCollectionState,
)
from praviar_pipeline.models.search_loop import CoverageGap
from praviar_pipeline.pipeline.runtime.evidence_artifacts import (
    build_coverage_gaps,
    build_evidence_adapter_results,
)
from praviar_pipeline.pipeline.runtime.evidence_graph import summarize_matter_graph
from praviar_pipeline.pipeline.runtime.evidence_policy import (
    resolve_required_record_components,
)
from praviar_pipeline.pipeline.runtime.matter_graph_state import (
    build_runtime_evidence_snapshot,
    build_runtime_matter_graph_snapshot,
)
from tests.claim_text_test_helpers import trusted_claim_text_fields


def test_resolve_required_record_components_filters_jurisdiction_specific_requirements():
    settings = SimpleNamespace(
        required_record_components=[],
        clearance_threshold_profile="world_class_us_ep",
    )
    coverage_context = SimpleNamespace(us_patents=0, ep_patents=2)

    required = resolve_required_record_components(settings, coverage_context)

    assert "us_file_wrapper_dossier" not in required
    assert "ep_register_context" in required


def test_build_coverage_gaps_dedupes_component_and_source_failures():
    report = SimpleNamespace(
        search_loop_result=SimpleNamespace(
            final_assessment=SimpleNamespace(
                gaps_identified=[
                    CoverageGap(
                        gap_type="source_failure",
                        description="Evidence source 'epo_search' did not complete successfully.",
                        suggested_action="retry",
                    )
                ]
            )
        )
    )
    coverage_context = SimpleNamespace(
        coverage_summary=SimpleNamespace(failed_source_names=["epo_search", "epo_search"])
    )
    record_completeness = SimpleNamespace(missing_components=["verification", "verification"])

    gaps = build_coverage_gaps(
        report=report,
        coverage_context=coverage_context,
        record_completeness=record_completeness,
    )

    assert len(gaps) == 2
    assert {gap.gap_type for gap in gaps} == {"missing_verification", "source_failure"}


def test_build_evidence_adapter_results_marks_failures_and_derives_extra_sources():
    report = SimpleNamespace(
        source_health=SimpleNamespace(
            entries=[
                SimpleNamespace(
                    source="epo_search",
                    status=SimpleNamespace(value="failed"),
                    error_message="timeout",
                ),
                SimpleNamespace(
                    source="bigquery",
                    status=SimpleNamespace(value="ok"),
                    error_message="",
                ),
            ]
        )
    )
    matter_evidence_index = SimpleNamespace(
        authoritative_source_names=["epo_search"],
        supporting_source_names=["bigquery"],
        patent_records=[],
    )
    evidence_artifacts = [
        EvidenceArtifact(
            artifact_id="a1",
            artifact_type=EvidenceArtifactType.SEARCH_HIT,
            source_name="epo_search",
            authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
        ),
        EvidenceArtifact(
            artifact_id="a2",
            artifact_type=EvidenceArtifactType.CLAIM_ANALYSIS,
            source_name="normalized_report",
            authority_tier=EvidenceAuthorityTier.DISCOVERY,
        ),
    ]

    results = build_evidence_adapter_results(
        report=report,
        matter_evidence_index=matter_evidence_index,
        evidence_artifacts=evidence_artifacts,
    )

    by_name = {result.adapter_name: result for result in results}
    assert by_name["epo_search"].warnings == ["timeout"]
    assert (
        by_name["epo_search"].freshness_note
        == "EPO search record captured during the current pipeline run."
    )
    assert by_name["epo_search"].adapter_kind.value == "search"
    assert by_name["epo_search"].status.value == "failed"
    assert by_name["epo_search"].collection_state.value == "failed"
    assert by_name["normalized_report"].authority_tier == EvidenceAuthorityTier.DISCOVERY
    assert by_name["normalized_report"].collection_state.value == "collected"
    assert by_name["normalized_report"].freshness_note == "Derived from normalized report evidence."


def test_build_evidence_adapter_results_splits_multi_source_artifacts_and_tracks_components():
    report = SimpleNamespace(
        source_health=SimpleNamespace(
            entries=[
                SimpleNamespace(
                    source="pubchem_sdq",
                    status=SimpleNamespace(value="ok"),
                    error_message="",
                ),
                SimpleNamespace(
                    source="bigquery",
                    status=SimpleNamespace(value="ok"),
                    error_message="",
                ),
                SimpleNamespace(
                    source="uspto_odp",
                    status=SimpleNamespace(value="ok"),
                    error_message="",
                ),
            ]
        )
    )
    matter_evidence_index = SimpleNamespace(
        authoritative_source_names=["uspto_odp"],
        supporting_source_names=["pubchem_sdq", "bigquery"],
        patent_records=[],
    )
    record_completeness = SimpleNamespace(
        required_components=["claims_text", "us_prosecution_context", "us_file_wrapper_dossier"]
    )
    evidence_artifacts = [
        EvidenceArtifact(
            artifact_id="a1",
            artifact_type=EvidenceArtifactType.SEARCH_HIT,
            source_name="pubchem_sdq,bigquery",
            authority_tier=EvidenceAuthorityTier.SUPPORTING,
            patent_id="US123",
        ),
        EvidenceArtifact(
            artifact_id="a2",
            artifact_type=EvidenceArtifactType.CLAIMS_TEXT,
            source_name="bigquery",
            authority_tier=EvidenceAuthorityTier.SUPPORTING,
            patent_id="US123",
        ),
        EvidenceArtifact(
            artifact_id="a3",
            artifact_type=EvidenceArtifactType.PROSECUTION_DOSSIER,
            source_name="uspto_odp",
            authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
            patent_id="US123",
        ),
    ]

    results = build_evidence_adapter_results(
        report=report,
        matter_evidence_index=matter_evidence_index,
        evidence_artifacts=evidence_artifacts,
        record_completeness=record_completeness,
    )

    by_name = {result.adapter_name: result for result in results}
    assert by_name["pubchem_sdq"].artifact_count == 1
    assert by_name["pubchem_sdq"].adapter_kind.value == "search"
    assert by_name["pubchem_sdq"].collection_state.value == "collected"
    assert by_name["pubchem_sdq"].covered_patent_ids == ["US123"]
    assert by_name["bigquery"].artifact_count == 2
    assert by_name["bigquery"].covered_components == ["claims_text"]
    assert by_name["bigquery"].expected_components == ["claims_text"]
    assert by_name["bigquery"].missing_components == []
    assert by_name["bigquery"].collection_state.value == "collected"
    assert by_name["uspto_odp"].covered_components == [
        "us_prosecution_context",
        "us_file_wrapper_dossier",
    ]
    assert by_name["uspto_odp"].expected_components == [
        "us_prosecution_context",
        "us_file_wrapper_dossier",
    ]
    assert by_name["uspto_odp"].missing_components == []
    assert by_name["uspto_odp"].required_before_clear is True
    assert by_name["uspto_odp"].target_patent_ids == ["US123"]
    assert by_name["uspto_odp"].supports_authoritative_findings is True


def test_build_evidence_adapter_results_adds_required_policy_adapters_even_without_artifacts():
    report = SimpleNamespace(source_health=SimpleNamespace(entries=[]))
    matter_evidence_index = SimpleNamespace(
        authoritative_source_names=[],
        supporting_source_names=[],
        patent_records=[
            SimpleNamespace(
                patent_id="EP123",
                source_names=["epo_search"],
                authoritative_source_names=["epo_search"],
                supporting_source_names=[],
                component_statuses=[
                    SimpleNamespace(
                        component="ep_register_context",
                        status=SimpleNamespace(value="missing"),
                        source_name="epo_register",
                        required_before_clear=True,
                    )
                ],
            )
        ],
    )
    record_completeness = SimpleNamespace(
        required_components=["ep_register_context", "orange_book_record"]
    )

    results = build_evidence_adapter_results(
        report=report,
        matter_evidence_index=matter_evidence_index,
        evidence_artifacts=[],
        record_completeness=record_completeness,
    )

    by_name = {result.adapter_name: result for result in results}
    assert by_name["epo_register"].status.value == "not_configured"
    assert by_name["epo_register"].collection_state.value == "failed"
    assert by_name["epo_register"].required_before_clear is True
    assert by_name["epo_register"].target_patent_ids == ["EP123"]
    assert by_name["epo_register"].missing_patent_ids == ["EP123"]
    assert by_name["epo_register"].expected_components == ["ep_register_context"]
    assert by_name["epo_register"].missing_components == ["ep_register_context"]
    assert by_name["epo_register"].warnings == [
        "source is not configured",
        "Required adapter was not queried or produced no artifacts for: ep_register_context.",
        "Missing expected record components: ep_register_context.",
    ]
    assert by_name["orange_book"].status.value == "not_configured"
    assert by_name["orange_book"].collection_state.value == "failed"
    assert by_name["orange_book"].expected_components == ["orange_book_record"]


def test_build_evidence_adapter_results_preserves_not_configured_source_health():
    report = SimpleNamespace(
        source_health=SimpleNamespace(
            entries=[
                SimpleNamespace(
                    source="patentsview",
                    status=SimpleNamespace(value="not_configured"),
                    error_message="PatentsView API key not configured",
                )
            ]
        )
    )
    matter_evidence_index = SimpleNamespace(
        authoritative_source_names=["patentsview"],
        supporting_source_names=[],
        patent_records=[],
    )

    results = build_evidence_adapter_results(
        report=report,
        matter_evidence_index=matter_evidence_index,
        evidence_artifacts=[],
    )

    patentsview = {result.adapter_name: result for result in results}["patentsview"]
    assert patentsview.status.value == "not_configured"
    assert patentsview.collection_state.value == "failed"
    assert patentsview.warnings == [
        "PatentsView API key not configured",
        "Required adapter was not queried or produced no artifacts for: claims_text.",
        "Missing expected record components: claims_text.",
    ]


def test_summarize_matter_graph_groups_nodes_and_edges():
    graph = MatterGraph(
        nodes=[
            MatterNode(
                node_id="compound:aspirin",
                node_type=MatterNodeType.COMPOUND_VARIANT,
                label="aspirin",
            ),
            MatterNode(
                node_id="patent:US1234567B2",
                node_type=MatterNodeType.PATENT,
                label="US1234567B2",
            ),
            MatterNode(
                node_id="family:fam-1",
                node_type=MatterNodeType.FAMILY,
                label="fam-1",
            ),
        ],
        edges=[
            MatterEdge(
                edge_type=MatterEdgeType.ROOTS,
                from_node_id="compound:aspirin",
                to_node_id="patent:US1234567B2",
            ),
            MatterEdge(
                edge_type=MatterEdgeType.BELONGS_TO_FAMILY,
                from_node_id="patent:US1234567B2",
                to_node_id="family:fam-1",
            ),
        ],
    )

    summary = summarize_matter_graph(graph, compound_name="aspirin")

    assert summary.root_compound == "aspirin"
    assert summary.node_counts_by_type == {
        "compound_variant": 1,
        "family": 1,
        "patent": 1,
    }
    assert summary.edge_counts_by_type == {
        "belongs_to_family": 1,
        "roots": 1,
    }
    assert summary.patent_node_ids == ["patent:US1234567B2"]
    assert summary.family_node_ids == ["family:fam-1"]


def test_build_runtime_matter_graph_snapshot_includes_patent_hits_before_analysis():
    graph, summary = build_runtime_matter_graph_snapshot(
        compound=SimpleNamespace(name="aspirin"),
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        analysis_failures=[],
        patent_hits=[
            SimpleNamespace(
                patent_id="US1234567B2",
                jurisdiction="US",
                application_number="US10/000001",
                family=SimpleNamespace(family_id="fam-1"),
                ptab_proceedings=[SimpleNamespace(proceeding_number="IPR2025-0001")],
                orange_book_listed=True,
            )
        ],
        prosecution_cache={},
        source_health=SourceHealth(entries=[]),
    )

    assert summary.root_compound == "aspirin"
    assert {node.node_type.value for node in graph.nodes} >= {
        "compound_variant",
        "patent",
        "application",
        "family",
        "ptab_matter",
        "orange_book_entry",
    }
    assert any(
        edge.edge_type.value == "prosecuted_as" and edge.to_node_id == "application:US10/000001"
        for edge in graph.edges
    )


def test_build_runtime_evidence_snapshot_tracks_live_adapter_coverage():
    patent_id = "US1234567B2"
    claims_text = "Claim 1. Example text."
    snapshot = build_runtime_evidence_snapshot(
        compound=SimpleNamespace(name="aspirin"),
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        analysis_failures=[],
        patent_hits=[
            PatentHit(
                patent_id=patent_id,
                jurisdiction="US",
                application_number="US10/000001",
                family=PatentFamily(
                    family_id="fam-1",
                    members=[PatentFamilyMember(country="US", doc_number="1234567", kind="B2")],
                ),
                ptab_proceedings=[PTABProceeding(proceeding_number="IPR2025-0001")],
                orange_book_listed=True,
                **trusted_claim_text_fields(
                    patent_id,
                    claims_text,
                    source=PatentSource.PATENTSVIEW,
                ),
                sources=[PatentSource.PATENTSVIEW],
                transactions=[],
            )
        ],
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
        settings=SimpleNamespace(
            required_record_components=["claims_text", "family_context", "us_file_wrapper_dossier"],
            clearance_threshold_profile="world_class_us_ep",
            matter_type="small_molecule",
            jurisdiction_policy="us_ep_core",
            source_authority_policy="official_plus_licensed",
        ),
    )

    by_name = {result.adapter_name: result for result in snapshot.evidence_adapter_results}
    assert by_name["patentsview"].status.value == "ok"
    assert by_name["patentsview"].artifact_count >= 1
    assert "claims_text" in by_name["patentsview"].covered_components
    assert by_name["patentsview"].collection_state.value == "collected"
    assert by_name["family_record"].status.value == "ok"
    assert by_name["family_record"].covered_components == ["family_context"]
    assert by_name["family_record"].collection_state.value == "collected"
    assert by_name["uspto_odp"].status.value == "not_configured"
    assert by_name["uspto_odp"].missing_components == ["us_file_wrapper_dossier"]
    assert by_name["uspto_odp"].collection_state.value == "failed"
    assert by_name["uspto_odp"].required_before_clear is True
    assert by_name["uspto_odp"].missing_patent_ids == ["US1234567B2"]
    collector_runs = {run.definition.collector_name: run for run in snapshot.collector_runs}
    assert collector_runs["patentsview"].collection_state.value == "collected"
    assert collector_runs["patentsview"].collection_targets[0].patent_id == "US1234567B2"
    assert collector_runs["uspto_odp"].collection_state.value == "failed"
    assert collector_runs["uspto_odp"].attempts[0].summary == (
        "Collector attempt failed and left required record targets unresolved."
    )
    assert snapshot.matter_store.matter_graph_summary.node_count >= 2
    assert snapshot.matter_store.collector_runs[0].definition.collector_name == "patentsview"
    assert (
        "us_file_wrapper_dossier" in snapshot.matter_store.record_completeness.required_components
    )


def test_build_runtime_evidence_snapshot_preserves_existing_collector_attempts():
    patent_hit = PatentHit(
        patent_id="US1234567B2",
        title="Aspirin composition",
        claims_text="1. A composition...",
        claims_text_source="patentsview",
        sources=[PatentSource.PATENTSVIEW],
    )
    existing_collectors = [
        EvidenceCollectorRun(
            definition=EvidenceCollectorDefinition(
                collector_name="patentsview",
                adapter_kind=EvidenceAdapterKind.SEARCH,
                authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                expected_components=["claims_text"],
            ),
            collection_state=EvidenceCollectionState.COLLECTED,
            required_before_clear=True,
            target_patent_ids=["US1234567B2"],
            covered_patent_ids=["US1234567B2"],
            expected_components=["claims_text"],
            covered_components=["claims_text"],
            attempts=[
                CollectionAttempt(
                    attempt_number=1,
                    status=SourceStatus.OK,
                    collection_state=EvidenceCollectionState.COLLECTED,
                    artifact_count=1,
                    summary="Initial PatentsView claims collection succeeded.",
                ),
                CollectionAttempt(
                    attempt_number=2,
                    status=SourceStatus.OK,
                    collection_state=EvidenceCollectionState.COLLECTED,
                    artifact_count=1,
                    summary="PatentsView claims collection was retried successfully.",
                ),
            ],
        )
    ]

    snapshot = build_runtime_evidence_snapshot(
        compound=SimpleNamespace(name="aspirin"),
        analyses=[],
        doe_assessments=[],
        invalidity_assessments=[],
        analysis_failures=[],
        patent_hits=[patent_hit],
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
        settings=SimpleNamespace(
            required_record_components=["claims_text"],
            clearance_threshold_profile="world_class_us_ep",
            matter_type="small_molecule",
            jurisdiction_policy="us_ep_core",
            source_authority_policy="official_plus_licensed",
        ),
        existing_collector_runs=existing_collectors,
    )

    collector_runs = {run.definition.collector_name: run for run in snapshot.collector_runs}
    assert collector_runs["patentsview"].attempts[0].attempt_number == 1
    assert collector_runs["patentsview"].attempts[1].attempt_number == 2
    assert collector_runs["patentsview"].attempts[1].summary == (
        "PatentsView claims collection was retried successfully."
    )

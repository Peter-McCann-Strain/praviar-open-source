"""Runtime evidence-snapshot construction.

This module consolidates the typed snapshot models, input normalisation
helpers, live-artifact synthesis, input preparation and the final snapshot
assembly used to build runtime evidence snapshots and matter graphs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

from praviar_pipeline.models.patent import has_trusted_claim_text_provenance
from praviar_pipeline.models.report import (
    AuthorityCoverage,
    EvidenceAdapterResult,
    EvidenceArtifact,
    EvidenceArtifactType,
    EvidenceAuthorityTier,
    EvidenceCollectorRun,
    MatterGraph,
    MatterGraphSummary,
    MatterStore,
    RecordCompleteness,
    RunObservability,
    SourceHealth,
    VerificationResult,
)
from praviar_pipeline.pipeline.report.evidence_index import build_matter_evidence_index
from praviar_pipeline.pipeline.report.prosecution_dossier import build_prosecution_dossiers
from praviar_pipeline.pipeline.runtime.decisioning_coverage import build_decision_coverage_context
from praviar_pipeline.pipeline.runtime.decisioning_outputs import (
    build_claim_program_summary,
    build_evidence_collection_plan,
    build_run_observability,
    populate_coverage_summary_from_index,
)
from praviar_pipeline.pipeline.runtime.evidence_artifacts import (
    build_coverage_gaps,
    build_evidence_adapter_results,
    build_evidence_artifacts,
)
from praviar_pipeline.pipeline.runtime.evidence_claims import build_claim_program_decisions
from praviar_pipeline.pipeline.runtime.evidence_collectors import (
    build_evidence_collector_runs,
    merge_evidence_collector_runs,
)
from praviar_pipeline.pipeline.runtime.evidence_graph import (
    build_matter_graph,
    summarize_matter_graph,
)
from praviar_pipeline.pipeline.runtime.evidence_policy import (
    build_authority_coverage,
    build_record_completeness,
    resolve_required_record_components,
)
from praviar_pipeline.pipeline.runtime.matter_store import (
    build_matter_store,
    build_record_contradictions,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(slots=True)
class RuntimeEvidenceSnapshot:
    matter_graph: MatterGraph = field(default_factory=MatterGraph)
    matter_graph_summary: MatterGraphSummary = field(default_factory=MatterGraphSummary)
    evidence_artifacts: list[EvidenceArtifact] = field(default_factory=list)
    evidence_adapter_results: list[EvidenceAdapterResult] = field(default_factory=list)
    collector_runs: list[EvidenceCollectorRun] = field(default_factory=list)
    matter_store: MatterStore = field(default_factory=MatterStore)


@dataclass(slots=True)
class PreparedRuntimeSnapshotInputs:
    report_stub: object
    detail_map: dict[str, object]
    coverage_context: object
    matter_evidence_index: object
    prosecution_dossiers: Sequence[object]
    record_completeness: object | None
    run_observability: RunObservability | None = None


def normalize_source_health(source_health) -> SourceHealth:
    if isinstance(source_health, SourceHealth):
        return source_health
    if isinstance(source_health, dict):
        return SourceHealth.model_validate(source_health)
    return SourceHealth(entries=list(getattr(source_health, "entries", []) or []))


def build_report_stub(
    *,
    compound,
    analyses: list,
    doe_assessments: list,
    invalidity_assessments: list,
    analysis_failures: list,
    normalized_source_health: SourceHealth,
    prosecution_dossiers: list,
    verification,
    critic_report,
    search_loop_result,
    data_limitations: list,
):
    return SimpleNamespace(
        compound=compound,
        patent_analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        source_health=normalized_source_health,
        analysis_failures=analysis_failures,
        prosecution_dossiers=prosecution_dossiers,
        verification=verification or VerificationResult(),
        critic_report=critic_report,
        search_loop_result=search_loop_result,
        data_limitations=data_limitations,
    )


def detail_map_from_patent_hits(patent_hits: list) -> dict[str, object]:
    return {
        getattr(hit, "patent_id", ""): hit for hit in patent_hits if getattr(hit, "patent_id", "")
    }


def enrich_runtime_coverage_context(coverage_context, *, analyses: list, patent_hits: list) -> None:
    if analyses or not patent_hits:
        return

    runtime_us_patents = sum(
        1
        for patent_hit in patent_hits
        if str(getattr(patent_hit, "jurisdiction", "") or "").upper() == "US"
    )
    runtime_ep_patents = sum(
        1
        for patent_hit in patent_hits
        if str(getattr(patent_hit, "jurisdiction", "") or "").upper() == "EP"
    )
    coverage_context.us_patents = max(coverage_context.us_patents, runtime_us_patents)
    coverage_context.ep_patents = max(coverage_context.ep_patents, runtime_ep_patents)


def primary_source_name(patent_hit) -> str:
    sources = list(getattr(patent_hit, "sources", []) or [])
    if not sources:
        return ""
    return getattr(sources[0], "value", str(sources[0] or ""))


def search_authority_tier(patent_hit) -> EvidenceAuthorityTier:
    source_names = {
        getattr(source, "value", str(source or "")).strip().lower()
        for source in list(getattr(patent_hit, "sources", []) or [])
        if getattr(source, "value", str(source or "")).strip()
    }
    if source_names.intersection({"patentsview", "epo_search"}):
        return EvidenceAuthorityTier.AUTHORITATIVE
    if source_names:
        return EvidenceAuthorityTier.SUPPORTING
    return EvidenceAuthorityTier.DISCOVERY


def extend_with_live_patent_hit_artifacts(
    evidence_artifacts: list[EvidenceArtifact],
    *,
    patent_hits: list,
    prosecution_cache: dict[str, dict[str, object]] | None,
) -> list[EvidenceArtifact]:
    by_key = {
        (artifact.artifact_type, artifact.patent_id, artifact.claim_number or 0): artifact
        for artifact in evidence_artifacts
    }
    extended = list(evidence_artifacts)
    prosecution_cache = prosecution_cache or {}

    def add_artifact(artifact: EvidenceArtifact) -> None:
        key = (artifact.artifact_type, artifact.patent_id, artifact.claim_number or 0)
        if key not in by_key:
            by_key[key] = artifact
            extended.append(artifact)

    for patent_hit in patent_hits:
        patent_id = getattr(patent_hit, "patent_id", "") or ""
        if not patent_id:
            continue
        jurisdiction = str(getattr(patent_hit, "jurisdiction", "") or "")
        family_id = str(getattr(getattr(patent_hit, "family", None), "family_id", "") or "")
        authority_tier = search_authority_tier(patent_hit)
        source_names = [
            getattr(source, "value", str(source or ""))
            for source in list(getattr(patent_hit, "sources", []) or [])
            if getattr(source, "value", str(source or ""))
        ]
        add_artifact(
            EvidenceArtifact(
                artifact_id=f"{patent_id}:search_hit",
                artifact_type=EvidenceArtifactType.SEARCH_HIT,
                source_name=",".join(source_names),
                authority_tier=authority_tier,
                jurisdiction=jurisdiction,
                patent_id=patent_id,
                family_id=family_id,
                summary="Patent was collected during runtime evidence gathering.",
                record_basis=source_names,
                linked_node_ids=[f"patent:{patent_id}"],
            )
        )
        if has_trusted_claim_text_provenance(patent_hit):
            claims_source = str(
                getattr(patent_hit, "claims_text_source", "") or ""
            ) or primary_source_name(patent_hit)
            add_artifact(
                EvidenceArtifact(
                    artifact_id=f"{patent_id}:claims_text",
                    artifact_type=EvidenceArtifactType.CLAIMS_TEXT,
                    source_name=claims_source,
                    authority_tier=authority_tier,
                    jurisdiction=jurisdiction,
                    patent_id=patent_id,
                    family_id=family_id,
                    summary="Claims text was collected during runtime evidence gathering.",
                    record_basis=["claims_text", "claim_text_provenance"],
                    linked_node_ids=[f"patent:{patent_id}"],
                )
            )
        if family_id:
            add_artifact(
                EvidenceArtifact(
                    artifact_id=f"{patent_id}:family_context",
                    artifact_type=EvidenceArtifactType.FAMILY_CONTEXT,
                    source_name="family_record",
                    authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                    jurisdiction=jurisdiction,
                    patent_id=patent_id,
                    family_id=family_id,
                    summary=(
                        "Patent family context was available during runtime evidence gathering."
                    ),
                    record_basis=["family_record"],
                    linked_node_ids=[f"patent:{patent_id}", f"family:{family_id}"],
                )
            )
        if prosecution_cache.get(patent_id):
            prosecution_context = prosecution_cache.get(patent_id) or {}
            raw_sections_available = prosecution_context.get("sections_available")
            sections_available = {
                str(section).strip()
                for section in (
                    raw_sections_available
                    if isinstance(raw_sections_available, (list, tuple, set))
                    else []
                )
                if str(section).strip()
            }
            raw_document_count = prosecution_context.get("file_wrapper_document_count", 0)
            try:
                file_wrapper_document_count = int(str(raw_document_count or 0))
            except ValueError:
                file_wrapper_document_count = 0
            record_basis = ["us_prosecution_context"]
            if "us_file_wrapper_dossier" in sections_available or file_wrapper_document_count > 0:
                record_basis.append("us_file_wrapper_dossier")
            add_artifact(
                EvidenceArtifact(
                    artifact_id=f"{patent_id}:prosecution",
                    artifact_type=EvidenceArtifactType.PROSECUTION_DOSSIER,
                    source_name="uspto_odp",
                    authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                    jurisdiction=jurisdiction,
                    patent_id=patent_id,
                    family_id=family_id,
                    summary=(
                        "U.S. prosecution context was collected during runtime evidence gathering."
                    ),
                    record_basis=record_basis,
                    linked_node_ids=[f"patent:{patent_id}"],
                )
            )
        if getattr(patent_hit, "ptab_proceedings", None):
            add_artifact(
                EvidenceArtifact(
                    artifact_id=f"{patent_id}:ptab",
                    artifact_type=EvidenceArtifactType.PTAB_RECORD,
                    source_name="ptab",
                    authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                    jurisdiction=jurisdiction,
                    patent_id=patent_id,
                    family_id=family_id,
                    summary="PTAB context was available during runtime evidence gathering.",
                    record_basis=["ptab_record"],
                    linked_node_ids=[f"patent:{patent_id}"],
                )
            )
        if getattr(patent_hit, "orange_book_listed", False):
            add_artifact(
                EvidenceArtifact(
                    artifact_id=f"{patent_id}:orange_book",
                    artifact_type=EvidenceArtifactType.ORANGE_BOOK_RECORD,
                    source_name="orange_book",
                    authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                    jurisdiction=jurisdiction,
                    patent_id=patent_id,
                    family_id=family_id,
                    summary="Orange Book context was available during runtime evidence gathering.",
                    record_basis=["orange_book_record"],
                    linked_node_ids=[f"patent:{patent_id}"],
                )
            )
        if jurisdiction == "EP" and (
            getattr(patent_hit, "designated_states", None)
            or getattr(patent_hit, "opposition_events", None)
        ):
            add_artifact(
                EvidenceArtifact(
                    artifact_id=f"{patent_id}:ep_register",
                    artifact_type=EvidenceArtifactType.EP_REGISTER_RECORD,
                    source_name="epo_register",
                    authority_tier=EvidenceAuthorityTier.AUTHORITATIVE,
                    jurisdiction=jurisdiction,
                    patent_id=patent_id,
                    family_id=family_id,
                    summary="EP register context was available during runtime evidence gathering.",
                    record_basis=["ep_register_context"],
                    linked_node_ids=[f"patent:{patent_id}"],
                )
            )
    return extended


def prepare_runtime_snapshot_inputs(
    *,
    compound,
    analyses: list,
    doe_assessments: list,
    invalidity_assessments: list,
    analysis_failures: list,
    patent_hits: list,
    prosecution_cache: dict[str, dict[str, object]] | None,
    source_health,
    verification=None,
    critic_report=None,
    search_loop_result=None,
    data_limitations: list | None = None,
    settings=None,
) -> PreparedRuntimeSnapshotInputs:
    normalized_source_health = normalize_source_health(source_health)
    prosecution_dossiers = build_prosecution_dossiers(
        analyses=analyses,
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache or {},
    )

    report_stub = build_report_stub(
        compound=compound,
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        analysis_failures=analysis_failures,
        normalized_source_health=normalized_source_health,
        prosecution_dossiers=prosecution_dossiers,
        verification=verification,
        critic_report=critic_report,
        search_loop_result=search_loop_result,
        data_limitations=data_limitations or [],
    )
    detail_map = detail_map_from_patent_hits(patent_hits)
    coverage_context = build_decision_coverage_context(report_stub, detail_map)
    enrich_runtime_coverage_context(
        coverage_context,
        analyses=analyses,
        patent_hits=patent_hits,
    )
    matter_evidence_index = build_matter_evidence_index(
        analyses=analyses,
        doe_assessments=doe_assessments,
        invalidity_assessments=invalidity_assessments,
        analysis_failures=analysis_failures,
        patent_hits=patent_hits,
        prosecution_dossiers=prosecution_dossiers,
        critic_report=critic_report,
        source_health=normalized_source_health,
    )

    record_completeness = None
    if settings is not None:
        required_record_components = resolve_required_record_components(
            settings,
            coverage_context,
        )
        populate_coverage_summary_from_index(
            coverage_context=coverage_context,
            matter_evidence_index=matter_evidence_index,
            required_record_components=required_record_components,
        )
        record_completeness = build_record_completeness(
            report=report_stub,
            coverage_context=coverage_context,
            settings=settings,
        )

    return PreparedRuntimeSnapshotInputs(
        report_stub=report_stub,
        detail_map=detail_map,
        coverage_context=coverage_context,
        matter_evidence_index=matter_evidence_index,
        prosecution_dossiers=prosecution_dossiers,
        record_completeness=record_completeness,
    )


def assemble_runtime_evidence_snapshot(
    *,
    compound,
    analyses: list,
    patent_hits: list,
    prosecution_cache: dict[str, dict[str, object]] | None,
    settings,
    existing_collector_runs: list | None,
    prepared: PreparedRuntimeSnapshotInputs,
) -> RuntimeEvidenceSnapshot:
    claim_program_decisions = build_claim_program_decisions(
        report=prepared.report_stub,
        detail_map=prepared.detail_map,
        coverage_context=prepared.coverage_context,
        intended_actions=list(getattr(settings, "intended_actions", []) or []),
        product_context=getattr(settings, "product_context", None),
        target_jurisdictions=list(getattr(settings, "target_jurisdictions", []) or []),
        development_stage=getattr(settings, "development_stage", ""),
        receipt_verification_keys=getattr(
            settings,
            "checkpoint_integrity_keys",
            None,
        ),
    )
    claim_program_summary = build_claim_program_summary(claim_program_decisions)
    coverage_gaps = (
        build_coverage_gaps(
            report=prepared.report_stub,
            coverage_context=prepared.coverage_context,
            record_completeness=prepared.record_completeness,
        )
        if prepared.record_completeness is not None
        else []
    )
    evidence_artifacts = build_evidence_artifacts(
        report=prepared.report_stub,
        matter_evidence_index=prepared.matter_evidence_index,
        claim_program_decisions=claim_program_decisions,
        coverage_gaps=coverage_gaps,
    )
    evidence_artifacts = extend_with_live_patent_hit_artifacts(
        evidence_artifacts,
        patent_hits=patent_hits,
        prosecution_cache=prosecution_cache,
    )
    evidence_adapter_results = build_evidence_adapter_results(
        report=prepared.report_stub,
        matter_evidence_index=prepared.matter_evidence_index,
        evidence_artifacts=evidence_artifacts,
        record_completeness=prepared.record_completeness,
    )
    evidence_collection_plan = (
        build_evidence_collection_plan(
            record_completeness=prepared.record_completeness,
            coverage_context=prepared.coverage_context,
            evidence_adapter_results=evidence_adapter_results,
            claim_program_summary=claim_program_summary,
        )
        if prepared.record_completeness is not None
        else []
    )
    collector_runs = build_evidence_collector_runs(
        evidence_adapter_results=evidence_adapter_results,
        evidence_collection_plan=evidence_collection_plan,
    )
    collector_runs = merge_evidence_collector_runs(
        existing_collector_runs=existing_collector_runs,
        latest_collector_runs=collector_runs,
    )
    matter_graph = build_matter_graph(
        report=prepared.report_stub,
        matter_evidence_index=prepared.matter_evidence_index,
        claim_program_decisions=claim_program_decisions,
        patent_hits=patent_hits,
        analyses=analyses,
    )
    matter_graph_summary = summarize_matter_graph(
        matter_graph,
        compound_name=getattr(compound, "name", ""),
    )
    authority_coverage = (
        build_authority_coverage(
            matter_evidence_index=prepared.matter_evidence_index,
            record_completeness=prepared.record_completeness,
            settings=settings,
        )
        if prepared.record_completeness is not None
        else AuthorityCoverage()
    )
    run_observability = (
        build_run_observability(
            coverage_context=prepared.coverage_context,
            report=prepared.report_stub,
            claim_program_summary=claim_program_summary,
            record_completeness=prepared.record_completeness,
            evidence_adapter_results=evidence_adapter_results,
        )
        if prepared.record_completeness is not None
        else RunObservability()
    )
    record_contradictions = build_record_contradictions(
        run_observability=run_observability,
        claim_program_summary=claim_program_summary,
        evidence_adapter_results=evidence_adapter_results,
    )
    matter_store = build_matter_store(
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        matter_evidence_index=prepared.matter_evidence_index,
        prosecution_dossiers=prepared.prosecution_dossiers,
        claim_program_decisions=claim_program_decisions,
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        collector_runs=collector_runs,
        evidence_collection_plan=evidence_collection_plan,
        coverage_gaps=coverage_gaps,
        authority_coverage=authority_coverage,
        record_completeness=prepared.record_completeness or RecordCompleteness(),
        run_observability=run_observability,
        record_contradictions=record_contradictions,
    )
    return RuntimeEvidenceSnapshot(
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        evidence_artifacts=evidence_artifacts,
        evidence_adapter_results=evidence_adapter_results,
        collector_runs=collector_runs,
        matter_store=matter_store,
    )

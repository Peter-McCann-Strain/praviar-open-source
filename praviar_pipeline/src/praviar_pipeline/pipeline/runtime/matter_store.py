"""Builders for the persistent runtime matter store."""

from __future__ import annotations

from praviar_pipeline.models.report import (
    MatterStore,
    MatterStoreCoverageGap,
    RecordContradiction,
    RecordContradictionSeverity,
)
from praviar_pipeline.pipeline.report.evidence_index_shared import unique_strings


def _contradiction_category(summary: str) -> str:
    lowered = summary.lower()
    if "authoritative legal status" in lowered or "ep register status" in lowered:
        return "authoritative_status_conflict"
    if "runtime budget" in lowered:
        return "runtime_budget"
    if "search loop" in lowered or "collection" in lowered:
        return "collection_incomplete"
    if "analysis" in lowered:
        return "analysis_inconsistency"
    if "claim" in lowered or "invalidity" in lowered:
        return "claim_program_conflict"
    return "record_contradiction"


def _contradiction_severity(summary: str) -> RecordContradictionSeverity:
    lowered = summary.lower()
    if "authoritative legal status" in lowered or "ep register status" in lowered:
        return RecordContradictionSeverity.HIGH
    if "runtime budget" in lowered:
        return RecordContradictionSeverity.HIGH
    if "blocking" in lowered or "high-risk" in lowered:
        return RecordContradictionSeverity.HIGH
    if "failed" in lowered or "required" in lowered:
        return RecordContradictionSeverity.MEDIUM
    return RecordContradictionSeverity.LOW


def build_record_contradictions(
    *,
    run_observability,
    claim_program_summary,
    evidence_adapter_results,
) -> list[RecordContradiction]:
    """Derive typed contradiction records from observability and claim state."""
    authoritative_failures = unique_strings(
        [
            result.adapter_name
            for result in evidence_adapter_results
            if result.supports_authoritative_findings
            and getattr(result.collection_state, "value", result.collection_state)
            in {"missing", "failed", "partial"}
        ]
    )
    affected_patent_ids = unique_strings(
        list(getattr(claim_program_summary, "blocking_patent_ids", []) or [])
        + list(getattr(claim_program_summary, "contested_patent_ids", []) or [])
        + list(getattr(claim_program_summary, "medium_risk_patent_ids", []) or [])
    )

    contradictions: list[RecordContradiction] = []
    for index, summary in enumerate(
        unique_strings(getattr(run_observability, "unresolved_contradictions", []) or []),
        start=1,
    ):
        contradictions.append(
            RecordContradiction(
                contradiction_id=f"record_contradiction_{index}",
                category=_contradiction_category(summary),
                summary=summary,
                severity=_contradiction_severity(summary),
                affected_patent_ids=affected_patent_ids,
                source_names=authoritative_failures,
            )
        )
    return contradictions


def build_matter_store(
    *,
    matter_graph,
    matter_graph_summary,
    matter_evidence_index,
    prosecution_dossiers,
    claim_program_decisions,
    evidence_artifacts,
    evidence_adapter_results,
    collector_runs,
    evidence_collection_plan,
    coverage_gaps,
    authority_coverage,
    record_completeness,
    run_observability,
    record_contradictions,
) -> MatterStore:
    """Build the persistent matter store shared across runtime stages."""
    normalized_coverage_gaps = [
        MatterStoreCoverageGap(
            gap_type=getattr(gap, "gap_type", ""),
            description=getattr(gap, "description", ""),
            suggested_action=getattr(gap, "suggested_action", ""),
        )
        for gap in list(coverage_gaps or [])
    ]
    return MatterStore(
        matter_graph=matter_graph,
        matter_graph_summary=matter_graph_summary,
        matter_evidence_index=matter_evidence_index,
        prosecution_dossiers=list(prosecution_dossiers or []),
        claim_program_decisions=list(claim_program_decisions or []),
        evidence_artifacts=list(evidence_artifacts or []),
        evidence_adapter_results=list(evidence_adapter_results or []),
        collector_runs=list(collector_runs or []),
        evidence_collection_plan=list(evidence_collection_plan or []),
        coverage_gaps=normalized_coverage_gaps,
        authority_coverage=authority_coverage,
        record_completeness=record_completeness,
        run_observability=run_observability,
        record_contradictions=list(record_contradictions or []),
    )

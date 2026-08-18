"""Builders for the evidence-fabric runtime substrate."""

from __future__ import annotations

from praviar_pipeline.pipeline.runtime.evidence_artifacts import (
    build_coverage_gaps,
    build_evidence_adapter_results,
    build_evidence_artifacts,
)
from praviar_pipeline.pipeline.runtime.evidence_claims import build_claim_program_decisions
from praviar_pipeline.pipeline.runtime.evidence_collectors import build_evidence_collector_runs
from praviar_pipeline.pipeline.runtime.evidence_graph import (
    build_matter_graph,
    summarize_matter_graph,
)
from praviar_pipeline.pipeline.runtime.evidence_policy import (
    build_authority_coverage,
    build_record_completeness,
    resolve_required_record_components,
)

__all__ = [
    "build_authority_coverage",
    "build_claim_program_decisions",
    "build_coverage_gaps",
    "build_evidence_adapter_results",
    "build_evidence_artifacts",
    "build_evidence_collector_runs",
    "build_matter_graph",
    "build_record_completeness",
    "resolve_required_record_components",
    "summarize_matter_graph",
]

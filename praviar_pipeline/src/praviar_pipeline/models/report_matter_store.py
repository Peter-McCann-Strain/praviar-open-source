"""Typed persistent matter-store models for the runtime evidence fabric."""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.models.report_decisioning import ProsecutionDossier
from praviar_pipeline.models.report_evidence_artifacts import (
    EvidenceAdapterResult,
    EvidenceArtifact,
    EvidenceCollectionDirective,
    EvidenceCollectorRun,
)
from praviar_pipeline.models.report_evidence_graph import MatterGraph, MatterGraphSummary
from praviar_pipeline.models.report_evidence_records import (
    AuthorityCoverage,
    ClaimProgramDecision,
    MatterEvidenceIndex,
    RecordCompleteness,
    RunObservability,
)


class RecordContradictionSeverity(enum.StrEnum):
    """Severity assigned to an unresolved record contradiction."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecordContradiction(BaseModel):
    """Typed contradiction record persisted inside the matter store."""

    model_config = ConfigDict(extra="forbid")

    contradiction_id: str
    category: str = ""
    summary: str = ""
    severity: RecordContradictionSeverity = RecordContradictionSeverity.MEDIUM
    affected_patent_ids: list[str] = Field(default_factory=list)
    affected_claim_ids: list[str] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)


class MatterStoreCoverageGap(BaseModel):
    """Coverage-gap record persisted in the matter store."""

    model_config = ConfigDict(extra="forbid")

    gap_type: str = ""
    description: str = ""
    suggested_action: str = ""


class MatterStore(BaseModel):
    """Persistent per-run evidence substrate shared across runtime stages."""

    model_config = ConfigDict(extra="forbid")

    matter_graph: MatterGraph = Field(default_factory=MatterGraph)
    matter_graph_summary: MatterGraphSummary = Field(default_factory=MatterGraphSummary)
    matter_evidence_index: MatterEvidenceIndex = Field(default_factory=MatterEvidenceIndex)
    prosecution_dossiers: list[ProsecutionDossier] = Field(default_factory=list)
    claim_program_decisions: list[ClaimProgramDecision] = Field(default_factory=list)
    evidence_artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    evidence_adapter_results: list[EvidenceAdapterResult] = Field(default_factory=list)
    collector_runs: list[EvidenceCollectorRun] = Field(default_factory=list)
    evidence_collection_plan: list[EvidenceCollectionDirective] = Field(default_factory=list)
    coverage_gaps: list[MatterStoreCoverageGap] = Field(default_factory=list)
    authority_coverage: AuthorityCoverage = Field(default_factory=AuthorityCoverage)
    record_completeness: RecordCompleteness = Field(default_factory=RecordCompleteness)
    run_observability: RunObservability = Field(default_factory=RunObservability)
    record_contradictions: list[RecordContradiction] = Field(default_factory=list)

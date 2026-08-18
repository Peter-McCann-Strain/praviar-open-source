"""Evidence-fabric and matter-graph report models."""

from __future__ import annotations

from praviar_pipeline.models.report_evidence_artifacts import (
    CollectionAttempt,
    CollectionTarget,
    EvidenceAdapterKind,
    EvidenceAdapterResult,
    EvidenceArtifact,
    EvidenceArtifactType,
    EvidenceAuthorityTier,
    EvidenceCollectionDirective,
    EvidenceCollectionState,
    EvidenceCollectorDefinition,
    EvidenceCollectorRun,
    EvidenceDirectivePriority,
)
from praviar_pipeline.models.report_evidence_graph import (
    MatterEdge,
    MatterEdgeType,
    MatterGraph,
    MatterGraphSummary,
    MatterNode,
    MatterNodeType,
)
from praviar_pipeline.models.report_evidence_records import (
    AuthorityCoverage,
    ClaimProgramDecision,
    FamilyEvidenceRecord,
    MatterEvidenceIndex,
    PatentEvidenceRecord,
    RecordCompleteness,
    RecordComponentStatus,
    RecordComponentStatusValue,
    RunObservability,
)
from praviar_pipeline.models.report_matter_store import (
    MatterStore,
    MatterStoreCoverageGap,
    RecordContradiction,
    RecordContradictionSeverity,
)

__all__ = [
    "AuthorityCoverage",
    "ClaimProgramDecision",
    "CollectionAttempt",
    "CollectionTarget",
    "EvidenceAdapterKind",
    "EvidenceAdapterResult",
    "EvidenceArtifact",
    "EvidenceArtifactType",
    "EvidenceAuthorityTier",
    "EvidenceCollectionDirective",
    "EvidenceCollectionState",
    "EvidenceCollectorDefinition",
    "EvidenceCollectorRun",
    "EvidenceDirectivePriority",
    "FamilyEvidenceRecord",
    "MatterEdge",
    "MatterEdgeType",
    "MatterEvidenceIndex",
    "MatterGraph",
    "MatterGraphSummary",
    "MatterNode",
    "MatterNodeType",
    "MatterStore",
    "MatterStoreCoverageGap",
    "PatentEvidenceRecord",
    "RecordCompleteness",
    "RecordComponentStatus",
    "RecordComponentStatusValue",
    "RecordContradiction",
    "RecordContradictionSeverity",
    "RunObservability",
]

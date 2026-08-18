"""Artifact and directive models for the evidence fabric."""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

from praviar_pipeline.models.report_common import SourceStatus


class EvidenceAuthorityTier(enum.StrEnum):
    """Authority tier assigned to an evidence artifact."""

    AUTHORITATIVE = "authoritative"
    SUPPORTING = "supporting"
    DISCOVERY = "discovery"


class EvidenceArtifactType(enum.StrEnum):
    """Canonical evidence artifact types captured during a run."""

    SEARCH_HIT = "search_hit"
    CLAIMS_TEXT = "claims_text"
    FAMILY_CONTEXT = "family_context"
    PROSECUTION_DOSSIER = "prosecution_dossier"
    EP_REGISTER_RECORD = "ep_register_record"
    PTAB_RECORD = "ptab_record"
    ORANGE_BOOK_RECORD = "orange_book_record"
    CLAIM_ANALYSIS = "claim_analysis"
    DOE_ASSESSMENT = "doe_assessment"
    INVALIDITY_ASSESSMENT = "invalidity_assessment"
    CRITIC_REVIEW = "critic_review"
    VERIFICATION = "verification"
    COVERAGE_GAP = "coverage_gap"


class EvidenceAdapterKind(enum.StrEnum):
    """Canonical adapter categories for the evidence fabric."""

    SEARCH = "search"
    LEGAL_RECORD = "legal_record"
    REGULATORY = "regulatory"
    PIPELINE = "pipeline"
    POLICY = "policy"
    DERIVED = "derived"


class EvidenceCollectionState(enum.StrEnum):
    """Collector state for one adapter against its expected record targets."""

    COLLECTED = "collected"
    PARTIAL = "partial"
    MISSING = "missing"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class EvidenceDirectivePriority(enum.StrEnum):
    """Priority assigned to an evidence-collection directive."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceArtifact(BaseModel):
    """Typed evidence unit emitted by the runtime evidence fabric."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    artifact_type: EvidenceArtifactType
    source_name: str = ""
    authority_tier: EvidenceAuthorityTier = EvidenceAuthorityTier.SUPPORTING
    jurisdiction: str = ""
    patent_id: str = ""
    family_id: str = ""
    claim_number: int | None = None
    summary: str = ""
    record_basis: list[str] = Field(default_factory=list)
    linked_node_ids: list[str] = Field(default_factory=list)


class EvidenceAdapterResult(BaseModel):
    """Standardized result shape for an evidence adapter invocation."""

    model_config = ConfigDict(extra="forbid")

    adapter_name: str
    adapter_kind: EvidenceAdapterKind = EvidenceAdapterKind.DERIVED
    authority_tier: EvidenceAuthorityTier = EvidenceAuthorityTier.SUPPORTING
    status: SourceStatus = SourceStatus.OK
    collection_state: EvidenceCollectionState = EvidenceCollectionState.COLLECTED
    required_before_clear: bool = False
    target_patent_ids: list[str] = Field(default_factory=list)
    covered_patent_ids: list[str] = Field(default_factory=list)
    missing_patent_ids: list[str] = Field(default_factory=list)
    artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rate_limit_remaining: int | None = None
    retry_after_seconds: float | None = None
    freshness_note: str = ""
    artifact_count: int = 0
    covered_components: list[str] = Field(default_factory=list)
    expected_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    supports_authoritative_findings: bool = False


class EvidenceCollectorDefinition(BaseModel):
    """Static collector metadata used by the runtime collection ledger."""

    model_config = ConfigDict(extra="forbid")

    collector_name: str
    adapter_kind: EvidenceAdapterKind = EvidenceAdapterKind.DERIVED
    authority_tier: EvidenceAuthorityTier = EvidenceAuthorityTier.SUPPORTING
    supports_authoritative_findings: bool = False
    expected_components: list[str] = Field(default_factory=list)


class CollectionTarget(BaseModel):
    """Patent-scoped collection target tracked by a runtime collector."""

    model_config = ConfigDict(extra="forbid")

    patent_id: str
    jurisdiction: str = ""
    required_components: list[str] = Field(default_factory=list)
    covered_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    required_before_clear: bool = False


class CollectionAttempt(BaseModel):
    """One deterministic collector attempt captured in the runtime ledger."""

    model_config = ConfigDict(extra="forbid")

    attempt_number: int = 1
    status: SourceStatus = SourceStatus.OK
    collection_state: EvidenceCollectionState = EvidenceCollectionState.COLLECTED
    artifact_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    rate_limit_remaining: int | None = None
    retry_after_seconds: float | None = None
    summary: str = ""


class EvidenceCollectorRun(BaseModel):
    """First-class runtime state for one collector over the current matter."""

    model_config = ConfigDict(extra="forbid")

    definition: EvidenceCollectorDefinition
    collection_state: EvidenceCollectionState = EvidenceCollectionState.COLLECTED
    required_before_clear: bool = False
    target_patent_ids: list[str] = Field(default_factory=list)
    covered_patent_ids: list[str] = Field(default_factory=list)
    missing_patent_ids: list[str] = Field(default_factory=list)
    expected_components: list[str] = Field(default_factory=list)
    covered_components: list[str] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    retry_budget_remaining: int = 0
    freshness_note: str = ""
    triggered_directive_ids: list[str] = Field(default_factory=list)
    collection_targets: list[CollectionTarget] = Field(default_factory=list)
    attempts: list[CollectionAttempt] = Field(default_factory=list)


class EvidenceCollectionDirective(BaseModel):
    """Actionable evidence-collection directive required to close record gaps."""

    model_config = ConfigDict(extra="forbid")

    directive_id: str
    directive_type: str
    priority: EvidenceDirectivePriority = EvidenceDirectivePriority.MEDIUM
    required_before_clear: bool = True
    target_patent_ids: list[str] = Field(default_factory=list)
    target_claim_ids: list[str] = Field(default_factory=list)
    target_jurisdictions: list[str] = Field(default_factory=list)
    recommended_adapters: list[str] = Field(default_factory=list)
    summary: str = ""
    rationale: str = ""

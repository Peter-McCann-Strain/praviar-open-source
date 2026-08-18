"""Analysis pipeline ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .mixins import TimestampMixin
from .models_base import AnalysisStatus, Base

_ECMASCRIPT_TRIM_SQL = (
    "chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(32) || "
    "chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || "
    "chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || "
    "chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || "
    "chr(8239) || chr(8287) || chr(12288) || chr(65279)"
)
_CAS_INPUT_REGEX_SQL = (
    "'^([Cc][Aa][Ss]([' || "
    f"{_ECMASCRIPT_TRIM_SQL} || "
    "']*([Rr][Nn]|[Nn][Oo]\\.?|#|:))?[' || "
    f"{_ECMASCRIPT_TRIM_SQL} || "
    "']*)?[0-9]{2,7}-[0-9]{2}-[0-9]$'"
)
_ECMASCRIPT_WHITESPACE_REGEX_SQL = f"'[' || {_ECMASCRIPT_TRIM_SQL} || ']'"

if TYPE_CHECKING:
    from .models_collaboration import (
        AnalysisReviewerDecision,
        AnalysisSearchRelevanceFeedback,
        AttorneyFeedbackRecord,
        Comment,
    )
    from .models_identity import Organization, User
    from .models_operations import ExportJob, Monitor


# ---------------------------------------------------------------------------
# Faithfulness-Aware UQ (T3-02) — shadow signal table
#
# Paper: Vashurin, Fadeeva et al., "Faithfulness-Aware Uncertainty Quantification
# for Fact-Checking the Output of Retrieval Augmented Generation",
# arXiv:2505.21072 (May 2025). Feasibility verdict on this codebase:
# VIABLE WITH ADAPTATION (see .claude/literature-findings.md finding #7).
#
# Shadow mode only: rows here never influence the report assembly or reviewer
# queue ordering until calibration data exists. They feed into the upcoming
# reviewer-override correlation study described in the upgrade plan.
# ---------------------------------------------------------------------------


class Analysis(TimestampMixin, Base):
    """Single FTO analysis run for a compound."""

    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="ck_analyses_completed_at_present",
        ),
        CheckConstraint(
            "input_type IN ('name', 'smiles', 'cas', 'inchi', 'inchikey')",
            name="ck_analyses_submitted_input_type",
        ),
        CheckConstraint(
            f"compound_input = btrim(compound_input, {_ECMASCRIPT_TRIM_SQL})",
            name="ck_analyses_compound_input_normalized",
        ),
        CheckConstraint(
            "input_type = CASE "
            f"WHEN compound_input ~ ({_CAS_INPUT_REGEX_SQL}) "
            "THEN 'cas' "
            "WHEN compound_input LIKE 'InChI=%' THEN 'inchi' "
            "WHEN compound_input ~ '^[A-Za-z]{14}-[A-Za-z]{10}-[A-Za-z]$' "
            "THEN 'inchikey' "
            f"WHEN compound_input !~ ({_ECMASCRIPT_WHITESPACE_REGEX_SQL}) "
            "AND compound_input ~ "
            "'^(\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|"
            "[-=#$:/\\\\.()]|%[0-9]{2}|[1-9]|\\*)+$' "
            "AND (regexp_count(compound_input, "
            "'\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|\\*') >= 2 "
            "OR (regexp_count(compound_input, "
            "'\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|\\*') = 1 "
            "AND compound_input ~ "
            "'\\[[^]]*\\]|\\*|[-=#$:/\\\\.()]|%[0-9]{2}|[1-9]')) "
            "THEN 'smiles' "
            "ELSE 'name' END",
            name="ck_analyses_submitted_input_type_matches_value",
        ),
        CheckConstraint(
            "(submitted_identity_confirmed AND "
            "submitted_identity_value IS NOT NULL AND "
            "submitted_identity_value = compound_input) OR "
            "(NOT submitted_identity_confirmed AND submitted_identity_value IS NULL)",
            name="ck_analyses_submitted_identity_confirmation",
        ),
        CheckConstraint(
            "(launch_idempotency_key_digest IS NULL "
            "AND launch_payload_digest IS NULL) OR "
            "(launch_idempotency_key_digest IS NOT NULL "
            "AND launch_payload_digest IS NOT NULL "
            "AND launch_idempotency_key_digest ~ '^[0-9a-f]{64}$' "
            "AND launch_payload_digest ~ '^[0-9a-f]{64}$')",
            name="ck_analyses_launch_idempotency_pair",
        ),
        CheckConstraint(
            "pipeline_reconciliation_generation >= 0",
            name="ck_analyses_pipeline_reconciliation_generation",
        ),
        Index("ix_analyses_org_status", "org_id", "status"),
        Index("ix_analyses_org_created", "org_id", "created_at"),
        Index(
            "ix_analyses_org_status_completed_at",
            "org_id",
            "status",
            "completed_at",
        ),
        Index("ix_analyses_compound_smiles", "compound_smiles"),
        Index("ix_analyses_pipeline_lease", "status", "pipeline_lease_expires_at"),
        Index(
            "uq_analyses_org_launch_idempotency",
            "org_id",
            "launch_idempotency_key_digest",
            unique=True,
            postgresql_where=text("launch_idempotency_key_digest IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))

    compound_input: Mapped[str] = mapped_column(Text)
    compound_name: Mapped[str] = mapped_column(String(500), default="")
    compound_smiles: Mapped[str] = mapped_column(Text, default="")
    compound_cid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_type: Mapped[str] = mapped_column(String(20), default="name")
    submitted_identity_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    submitted_identity_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    launch_idempotency_key_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    launch_payload_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    pipeline_reconciliation_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    pipeline_reconciliation_dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=AnalysisStatus.PENDING,
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    pipeline_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    pipeline_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    report_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    overall_risk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blocking_patents_count: Mapped[int] = mapped_column(Integer, default=0)
    total_patents_found: Mapped[int] = mapped_column(Integer, default=0)
    executive_summary: Mapped[str] = mapped_column(Text, default="")

    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pipeline_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    flagged_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    share_active_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    share_active_grant_count: Mapped[int] = mapped_column(Integer, default=0)
    share_view_count: Mapped[int] = mapped_column(Integer, default=0)
    share_last_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completion_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("batch_analyses.id", ondelete="SET NULL"), nullable=True
    )

    organization: Mapped[Organization] = relationship(lazy="raise", back_populates="analyses")
    initiated_by_user: Mapped[User | None] = relationship(
        lazy="raise", back_populates="analyses", foreign_keys=[initiated_by]
    )
    pipeline_events: Mapped[list[PipelineEvent]] = relationship(
        lazy="raise",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list[Comment]] = relationship(
        lazy="raise",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    export_jobs: Mapped[list[ExportJob]] = relationship(
        lazy="raise",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    monitors: Mapped[list[Monitor]] = relationship(
        lazy="raise",
        back_populates="source_analysis",
        foreign_keys="[Monitor.source_analysis_id]",
    )
    reviewer_decisions: Mapped[list[AnalysisReviewerDecision]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        foreign_keys="[AnalysisReviewerDecision.analysis_id]",
    )
    attorney_feedback: Mapped[list[AttorneyFeedbackRecord]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        foreign_keys="[AttorneyFeedbackRecord.analysis_id]",
    )
    search_relevance_feedback: Mapped[list[AnalysisSearchRelevanceFeedback]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        foreign_keys="[AnalysisSearchRelevanceFeedback.analysis_id]",
    )


class Compound(Base):
    """Deduplicated compound records across all analyses."""

    __tablename__ = "compounds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_smiles: Mapped[str] = mapped_column(Text, index=True)
    inchi_key: Mapped[str] = mapped_column(String(27), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500), default="")
    molecular_formula: Mapped[str] = mapped_column(String(200), default="")
    molecular_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    functional_groups: Mapped[list] = mapped_column(JSONB, default=list)
    pubchem_cid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    first_analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    analysis_count: Mapped[int] = mapped_column(Integer, default=1)


class OrganizationCompound(Base):
    """Organization-local usage metadata for a globally deduplicated compound."""

    __tablename__ = "organization_compounds"
    __table_args__ = (
        CheckConstraint(
            "analysis_count > 0",
            name="ck_organization_compounds_analysis_count_positive",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    compound_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("compounds.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str] = mapped_column(String(500), default="", server_default="")
    first_analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    analysis_count: Mapped[int] = mapped_column(Integer, default=1)


Index(
    "ix_organization_compounds_org_first",
    OrganizationCompound.org_id,
    OrganizationCompound.first_analyzed_at.desc(),
    OrganizationCompound.compound_id,
)


class PipelineEvent(Base):
    """Real-time pipeline progress events for SSE streaming."""

    __tablename__ = "pipeline_events"
    __table_args__ = (Index("ix_pipeline_events_analysis", "analysis_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    step_number: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(lazy="raise", back_populates="pipeline_events")


class ConfigPreset(Base):
    """Named pipeline configuration preset scoped to an organization."""

    __tablename__ = "config_presets"
    __table_args__ = (Index("ix_config_presets_org_default", "org_id", "is_default"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(lazy="raise", back_populates="config_presets")


class FaithfulnessScore(Base):
    """Per-(claim sentence, evidence span) entailment verdict for an analysis.

    Shadow-mode telemetry from the T3-02 Faithfulness-Aware UQ pass. One row per
    cited evidence sentence inside an analysis report. The verdict column holds
    the NLI label (ENTAILED, NEUTRAL, or CONTRADICTS) and ``confidence`` holds
    the model's self-reported probability in the 0.0 to 1.0 range.

    The table carries its own RLS policy (``org_isolation``) applied in migration
    ``e9f4a2b7c3d5``. PostgreSQL RLS does not propagate through foreign keys, so the
    policy must be declared on this table directly, not inherited from ``analyses``.
    ``analysis_id`` cascades on delete so removing an analysis also drops its
    faithfulness rows.
    """

    __tablename__ = "faithfulness_scores"
    __table_args__ = (
        Index("ix_faithfulness_scores_analysis", "analysis_id"),
        Index("ix_faithfulness_scores_org", "org_id"),
        Index(
            "ix_faithfulness_scores_analysis_finding",
            "analysis_id",
            "finding_index",
            "evidence_index",
        ),
        UniqueConstraint(
            "analysis_id",
            "finding_index",
            "evidence_index",
            "model_id",
            name="uq_faithfulness_scores_analysis_pair_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    finding_index: Mapped[int] = mapped_column(Integer)
    evidence_index: Mapped[int] = mapped_column(Integer)
    claim_sentence: Mapped[str] = mapped_column(Text)
    evidence_span: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

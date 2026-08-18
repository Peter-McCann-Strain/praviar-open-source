"""Operational ORM models for audit, exports, monitoring, and billing events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
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
from .models_base import AnalysisStatus, Base, ExportFormat, ExportStatus, MonitorSchedule

if TYPE_CHECKING:
    from .models_analysis import Analysis
    from .models_identity import Organization, User


class AuditLog(Base):
    """Immutable audit trail for compliance."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "org_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(lazy="raise", back_populates="audit_logs")


class ClaimedUseErasureAuthorizationRecord(Base):
    """Append-only database authority consumed by legal-ledger erasure."""

    __tablename__ = "claimed_use_erasure_authorizations"
    __table_args__ = (
        Index(
            "ix_claimed_use_erasure_authorizations_org_created",
            "org_id",
            "created_at",
        ),
        CheckConstraint(
            "actor_kind IN ('platform_superadmin', 'scheduled_system')",
            name="ck_claimed_use_erasure_authorizations_actor_kind",
        ),
        CheckConstraint(
            "(actor_kind = 'platform_superadmin' AND actor_user_id IS NOT NULL) OR "
            "(actor_kind = 'scheduled_system' AND actor_user_id IS NULL)",
            name="ck_claimed_use_erasure_authorizations_actor_binding",
        ),
        CheckConstraint(
            "receipt_count >= 0",
            name="ck_claimed_use_erasure_authorizations_receipt_count",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
    )
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    receipt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WeeklyDigestDelivery(TimestampMixin, Base):
    """Durable at-most-once provider boundary for one user and weekly period."""

    __tablename__ = "weekly_digest_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "user_id",
            "period_start",
            name="uq_weekly_digest_delivery_user_period",
        ),
        UniqueConstraint(
            "submission_id",
            name="uq_weekly_digest_delivery_submission",
        ),
        CheckConstraint(
            "period_end = period_start + interval '7 days'",
            name="ck_weekly_digest_delivery_period",
        ),
        CheckConstraint(
            "state IN ('prepared', 'dispatching', 'outcome_unknown', "
            "'provider_accepted', 'rejected', 'cancelled')",
            name="ck_weekly_digest_delivery_state",
        ),
        CheckConstraint(
            "reconciliation_attempt_count >= 0",
            name="ck_weekly_digest_delivery_reconcile_count",
        ),
        CheckConstraint(
            "(unsubscribe_token_digest IS NULL) = (unsubscribe_expires_at IS NULL)",
            name="ck_weekly_digest_delivery_token_pair",
        ),
        CheckConstraint(
            "unsubscribe_used_at IS NULL OR unsubscribe_token_digest IS NOT NULL",
            name="ck_weekly_digest_delivery_token_use",
        ),
        CheckConstraint(
            "(state = 'prepared' AND provider_attempt_started_at IS NULL "
            "AND recipient_email IS NULL AND unsubscribe_token_digest IS NULL) OR "
            "(state <> 'prepared' AND "
            "(state = 'cancelled' OR provider_attempt_started_at IS NOT NULL))",
            name="ck_weekly_digest_delivery_attempt_boundary",
        ),
        CheckConstraint(
            "(state = 'prepared' AND recipient_email IS NULL "
            "AND unsubscribe_token_digest IS NULL) OR "
            "(state IN ('dispatching', 'outcome_unknown') "
            "AND recipient_email IS NOT NULL "
            "AND unsubscribe_token_digest IS NOT NULL) OR "
            "(state = 'provider_accepted' AND recipient_email IS NULL "
            "AND unsubscribe_token_digest IS NOT NULL) OR "
            "(state IN ('rejected', 'cancelled') AND recipient_email IS NULL "
            "AND unsubscribe_token_digest IS NULL)",
            name="ck_weekly_digest_delivery_active_payload",
        ),
        CheckConstraint(
            "(state = 'provider_accepted' AND provider_message_id IS NOT NULL "
            "AND provider_accepted_at IS NOT NULL) OR "
            "(state <> 'provider_accepted' AND provider_message_id IS NULL "
            "AND provider_accepted_at IS NULL)",
            name="ck_weekly_digest_delivery_provider_acceptance",
        ),
        CheckConstraint(
            "(state IN ('rejected', 'cancelled') AND terminal_at IS NOT NULL) OR "
            "(state NOT IN ('rejected', 'cancelled') AND terminal_at IS NULL)",
            name="ck_weekly_digest_delivery_terminal",
        ),
        Index(
            "ix_weekly_digest_deliveries_org_due",
            "org_id",
            "state",
            "reconciliation_next_attempt_at",
        ),
        Index(
            "ix_weekly_digest_deliveries_org_period",
            "org_id",
            "period_start",
            "user_id",
        ),
        Index(
            "uq_weekly_digest_deliveries_token_digest",
            "unsubscribe_token_digest",
            unique=True,
            postgresql_where=text("unsubscribe_token_digest IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="prepared",
        server_default="prepared",
    )
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unsubscribe_token_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unsubscribe_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    unsubscribe_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_attempt_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reconciliation_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    reconciliation_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reconciliation_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_org_status", "org_id", "status"),
        Index("ix_export_jobs_analysis", "analysis_id"),
        Index("ix_export_jobs_user_status", "user_id", "status"),
        Index("ix_export_jobs_processing_lease", "status", "processing_lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    format: Mapped[ExportFormat] = mapped_column(
        Enum(ExportFormat, values_callable=lambda obj: [e.value for e in obj])
    )
    status: Mapped[ExportStatus] = mapped_column(
        Enum(ExportStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ExportStatus.PENDING,
    )
    sections: Mapped[list] = mapped_column(JSONB, default=list)
    audience: Mapped[str] = mapped_column(String(32), server_default="full", default="full")
    manifest_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    file_url: Mapped[str] = mapped_column(Text, default="")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    retry_attempts: Mapped[int] = mapped_column(Integer, default=0)
    processing_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    processing_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    superseded_reason: Mapped[str] = mapped_column(Text, default="")
    superseded_conclusion_ids: Mapped[list] = mapped_column(JSONB, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(lazy="raise", back_populates="export_jobs")


class Monitor(Base):
    """Compound monitoring schedule for periodic patent landscape scanning."""

    __tablename__ = "monitors"
    __table_args__ = (
        Index("ix_monitors_org_active", "org_id", "is_active"),
        CheckConstraint(
            "conclusion_status IN ('unbound', 'fresh', 'review_required', 'reassessed')",
            name="ck_monitors_conclusion_status",
        ),
        Index(
            "uq_monitors_org_source_analysis_id",
            "org_id",
            "source_analysis_id",
            unique=True,
            postgresql_where=text("source_analysis_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"),
        nullable=True,
    )
    compound_smiles: Mapped[str] = mapped_column(Text)
    compound_name: Mapped[str] = mapped_column(String(500), default="")
    source_report_id: Mapped[str] = mapped_column(String(100), default="")
    source_trust_mode: Mapped[str] = mapped_column(String(20), default="")
    schedule: Mapped[MonitorSchedule] = mapped_column(
        Enum(MonitorSchedule, values_callable=lambda obj: [e.value for e in obj]),
        default=MonitorSchedule.WEEKLY,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    jurisdiction_bundle: Mapped[str] = mapped_column(String(50), default="custom")
    target_jurisdictions: Mapped[list] = mapped_column(JSONB, default=list)
    strategy_version: Mapped[str] = mapped_column(String(50), default="2026-04-monitor-v1")
    monitoring_strategy: Mapped[dict] = mapped_column(JSONB, default=dict)
    watch_targets: Mapped[list] = mapped_column(JSONB, default=list)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_full_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_run_mode: Mapped[str] = mapped_column(String(30), default="")
    last_run_status: Mapped[str] = mapped_column(String(30), default="")
    last_run_summary: Mapped[str] = mapped_column(Text, default="")
    scan_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, default=None
    )
    scan_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_patent_count: Mapped[int] = mapped_column(Integer, default=0)
    cached_patent_ids: Mapped[list] = mapped_column(JSONB, default=list)
    last_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    conclusion_status: Mapped[str] = mapped_column(
        String(32),
        default="unbound",
        server_default="unbound",
    )
    stale_conclusions: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    alerts: Mapped[list[MonitorAlert]] = relationship(
        lazy="raise",
        back_populates="monitor",
        cascade="all, delete-orphan",
    )
    source_analysis: Mapped[Analysis | None] = relationship(
        lazy="raise",
        back_populates="monitors",
        foreign_keys=[source_analysis_id],
    )

    @property
    def stale_conclusion_count(self) -> int:
        return len(self.stale_conclusions or [])


class MonitorAlert(Base):
    """Alert generated when monitoring detects new patents for a compound."""

    __tablename__ = "monitor_alerts"
    __table_args__ = (
        Index("ix_monitor_alerts_org_created", "org_id", "created_at"),
        Index("ix_monitor_alerts_monitor_dismissed", "monitor_id", "dismissed", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    alert_type: Mapped[str] = mapped_column(String(50), default="new_patent_delta")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    summary: Mapped[str] = mapped_column(Text, default="")
    strategy_mode: Mapped[str] = mapped_column(String(30), default="")
    new_patent_ids: Mapped[list] = mapped_column(JSONB, default=list)
    new_event_ids: Mapped[list] = mapped_column(JSONB, default=list)
    jurisdiction_deltas: Mapped[dict] = mapped_column(JSONB, default=dict)
    affected_conclusions: Mapped[list] = mapped_column(JSONB, default=list)
    new_patent_count: Mapped[int] = mapped_column(Integer, default=0)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    monitor: Mapped[Monitor] = relationship(lazy="raise", back_populates="alerts")

    @property
    def stale_conclusion_count(self) -> int:
        return len(self.affected_conclusions or [])


class MonitorConclusionReassessment(TimestampMixin, Base):
    """Durable counsel disposition of a monitoring-invalidated conclusion.

    The source analysis owns the legal record. ``monitor_id`` is intentionally
    nullable so deleting a fully resolved watch cannot erase the reassessment
    evidence while the source report continues to exist.
    """

    __tablename__ = "monitor_conclusion_reassessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'reaffirmed', 'superseded', 'withdrawn')",
            name="ck_monitor_conclusion_reassessments_status",
        ),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL "
            "AND resolved_by_user_id IS NULL AND attestation_accepted = false "
            "AND reviewer_role = '' AND reviewer_name = '' AND reviewer_email = '' "
            "AND resolution_note = '' AND attestation_version = '' "
            "AND attestation_statement = '' AND replacement_analysis_id IS NULL) OR "
            "(status <> 'open' AND resolved_at IS NOT NULL "
            "AND attestation_accepted = true "
            "AND reviewer_role = 'attorney' "
            "AND length(btrim(reviewer_name)) > 0 "
            "AND length(btrim(reviewer_email)) > 0 "
            "AND length(btrim(resolution_note)) >= 20 "
            "AND length(btrim(attestation_version)) > 0 "
            "AND length(btrim(attestation_statement)) > 0)",
            name="ck_monitor_conclusion_reassessments_resolution",
        ),
        CheckConstraint(
            "length(btrim(conclusion_id)) > 0 "
            "AND length(btrim(conclusion_type)) > 0 "
            "AND length(btrim(conclusion_label)) > 0 "
            "AND dependency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_monitor_conclusion_reassessments_identity",
        ),
        CheckConstraint(
            "latest_observed_at >= invalidated_at "
            "AND (resolved_at IS NULL OR resolved_at >= invalidated_at)",
            name="ck_monitor_conclusion_reassessments_chronology",
        ),
        Index(
            "ix_monitor_conclusion_reassessments_org_analysis_status",
            "org_id",
            "source_analysis_id",
            "status",
        ),
        Index(
            "ix_monitor_conclusion_reassessments_org_monitor_status",
            "org_id",
            "monitor_id",
            "status",
        ),
        Index(
            "uq_monitor_conclusion_reassessments_open_episode",
            "org_id",
            "monitor_id",
            "conclusion_id",
            unique=True,
            postgresql_where=text("status = 'open' AND monitor_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    monitor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitors.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_report_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    conclusion_id: Mapped[str] = mapped_column(String(160), nullable=False)
    conclusion_type: Mapped[str] = mapped_column(String(64), nullable=False)
    conclusion_label: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_outcome: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    dependency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    trigger_evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    invalidated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    latest_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewer_role: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    reviewer_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    resolution_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attestation_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    attestation_statement: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attestation_accepted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    replacement_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_analysis: Mapped[Analysis] = relationship(
        lazy="raise",
        foreign_keys=[source_analysis_id],
    )
    replacement_analysis: Mapped[Analysis | None] = relationship(
        lazy="raise",
        foreign_keys=[replacement_analysis_id],
    )
    reviewer: Mapped[User | None] = relationship(
        lazy="raise",
        foreign_keys=[resolved_by_user_id],
    )


class BatchAnalysis(TimestampMixin, Base):
    """Group of analyses for multi-compound batch processing."""

    __tablename__ = "batch_analyses"
    __table_args__ = (
        CheckConstraint(
            "(launch_idempotency_key_digest IS NULL "
            "AND launch_payload_digest IS NULL) OR "
            "(launch_idempotency_key_digest IS NOT NULL "
            "AND launch_payload_digest IS NOT NULL "
            "AND launch_idempotency_key_digest ~ '^[0-9a-f]{64}$' "
            "AND launch_payload_digest ~ '^[0-9a-f]{64}$')",
            name="ck_batch_analyses_launch_idempotency_pair",
        ),
        Index("ix_batch_analyses_org", "org_id"),
        Index(
            "uq_batch_analyses_org_launch_idempotency",
            "org_id",
            "launch_idempotency_key_digest",
            unique=True,
            postgresql_where=text("launch_idempotency_key_digest IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), default="")
    total_compounds: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=AnalysisStatus.PENDING,
    )
    analysis_ids: Mapped[list] = mapped_column(JSONB, default=list)
    launch_idempotency_key_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    launch_payload_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )


class AnalysisCreditLedger(Base):
    """Append-only purchased-credit ledger for one-time analysis packs."""

    __tablename__ = "analysis_credit_ledger"
    __table_args__ = (
        Index("ix_analysis_credit_ledger_org_created", "org_id", "created_at"),
        Index("ix_analysis_credit_ledger_org_kind", "org_id", "kind"),
        CheckConstraint(
            "kind IN ('purchase', 'consume', 'refund')",
            name="ck_analysis_credit_ledger_kind",
        ),
        CheckConstraint(
            "((kind IN ('purchase', 'refund') AND credits_delta > 0) OR "
            "(kind = 'consume' AND credits_delta < 0))",
            name="ck_analysis_credit_ledger_delta_sign",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    credits_delta: Mapped[int] = mapped_column(Integer)
    credit_pack_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditCapacityRequest(TimestampMixin, Base):
    """Durable request for an administrator to add Report Credit capacity."""

    __tablename__ = "credit_capacity_requests"
    __table_args__ = (
        Index(
            "ix_credit_capacity_requests_org_status_requested",
            "org_id",
            "status",
            "requested_at",
            "id",
        ),
        Index(
            "ix_credit_capacity_requests_requester_requested",
            "org_id",
            "requester_user_id",
            "requested_at",
        ),
        Index(
            "ix_credit_capacity_requests_fulfillment_ledger",
            "fulfillment_credit_ledger_id",
        ),
        CheckConstraint(
            "requested_reports BETWEEN 1 AND 30",
            name="ck_credit_capacity_requests_reports",
        ),
        CheckConstraint(
            "source IN ('analysis_launch', 'capacity_watch', 'launch_retry')",
            name="ck_credit_capacity_requests_source",
        ),
        CheckConstraint(
            "status IN ('pending', 'fulfilled', 'declined')",
            name="ck_credit_capacity_requests_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL "
            "AND resolved_by_user_id IS NULL "
            "AND fulfillment_credit_ledger_id IS NULL) OR "
            "(status = 'fulfilled' AND resolved_at IS NOT NULL "
            "AND (resolved_by_user_id IS NOT NULL "
            "OR fulfillment_credit_ledger_id IS NOT NULL)) OR "
            "(status = 'declined' AND resolved_at IS NOT NULL "
            "AND resolved_by_user_id IS NOT NULL "
            "AND fulfillment_credit_ledger_id IS NULL)",
            name="ck_credit_capacity_requests_resolution",
        ),
        CheckConstraint(
            "resolution_note IS NULL OR char_length(resolution_note) <= 1000",
            name="ck_credit_capacity_requests_note_length",
        ),
        CheckConstraint(
            "status != 'declined' OR "
            "(resolution_note IS NOT NULL "
            "AND char_length(btrim(resolution_note)) >= 4)",
            name="ck_credit_capacity_requests_decline_reason",
        ),
        CheckConstraint(
            "notified_admins > 0",
            name="ck_credit_capacity_requests_notified_admins",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    requester_name: Mapped[str] = mapped_column(String(255))
    requested_reports: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    notified_admins: Mapped[int] = mapped_column(Integer)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    fulfillment_credit_ledger_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_credit_ledger.id", ondelete="SET NULL"),
        nullable=True,
    )


class StripeEvent(Base):
    """Idempotency log for Stripe webhook events."""

    __tablename__ = "stripe_events"
    __table_args__ = (
        Index("ix_stripe_events_processing_lease", "processed", "processing_lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_event_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=True)
    processing_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    processing_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

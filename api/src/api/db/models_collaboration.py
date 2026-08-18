"""Collaboration, feedback, and notification ORM models."""

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
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .mixins import TimestampMixin
from .models_base import Base, NotificationType, ReviewStatus

if TYPE_CHECKING:
    from .models_analysis import Analysis
    from .models_identity import User


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_org_analysis_created", "org_id", "analysis_id", "created_at"),
        Index("ix_comments_analysis_created", "analysis_id", "created_at"),
        Index("ix_comments_user_id", "user_id"),
        Index("ix_comments_assigned_to", "assigned_to"),
        Index("ix_comments_resolved_by", "resolved_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(50), default="analysis")
    target_id: Mapped[str] = mapped_column(String(100), default="")
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list] = mapped_column(ARRAY(String), default=list)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped[Analysis] = relationship(lazy="raise", back_populates="comments")
    user: Mapped[User | None] = relationship(
        lazy="raise", back_populates="comments", foreign_keys=[user_id]
    )
    resolved_by_user: Mapped[User | None] = relationship(lazy="raise", foreign_keys=[resolved_by])
    assigned_to_user: Mapped[User | None] = relationship(lazy="raise", foreign_keys=[assigned_to])
    assigned_by_user: Mapped[User | None] = relationship(lazy="raise", foreign_keys=[assigned_by])
    parent: Mapped[Comment | None] = relationship(
        lazy="raise", back_populates="replies", remote_side=[id]
    )
    replies: Mapped[list[Comment]] = relationship(lazy="raise", back_populates="parent")


class CommentAssignmentEvent(Base):
    """Append-only audit trail for comment assignment workflow changes."""

    __tablename__ = "comment_assignment_events"
    __table_args__ = (
        Index("ix_comment_assignment_events_comment_created", "comment_id", "created_at"),
        Index(
            "ix_comment_assignment_events_analysis_org_created",
            "analysis_id",
            "org_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    comment: Mapped[Comment] = relationship(lazy="raise")


class CommentThreadEscalation(Base):
    """Persisted thread-level escalation state for comment queues."""

    __tablename__ = "comment_thread_escalations"
    __table_args__ = (
        Index("ix_comment_thread_escalations_comment_org", "comment_id", "org_id", unique=True),
        Index("ix_comment_thread_escalations_analysis_org", "analysis_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    escalated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    escalation_status: Mapped[str] = mapped_column(String(32), default="escalated", nullable=False)
    escalated_to_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    review_handoff_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="SET NULL"), nullable=True
    )

    comment: Mapped[Comment] = relationship(lazy="raise", foreign_keys=[comment_id])


class AttorneyFeedbackRecord(Base):
    """Attorney review/correction of an FTO analysis."""

    __tablename__ = "attorney_feedback"
    __table_args__ = (
        Index("ix_attorney_feedback_analysis_id", "analysis_id"),
        Index("ix_attorney_feedback_org_id", "org_id"),
        Index("ix_attorney_feedback_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    overall_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level_correct: Mapped[bool] = mapped_column(Boolean, default=True)
    corrected_risk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    corrections: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisSearchRelevanceFeedback(TimestampMixin, Base):
    """Attorney relevance label for one patent in one immutable search plan."""

    __tablename__ = "analysis_search_relevance_feedback"
    __table_args__ = (
        CheckConstraint(
            "relevance IN ('relevant', 'not_relevant', 'uncertain')",
            name="ck_analysis_search_relevance_feedback_label",
        ),
        CheckConstraint(
            "query_plan_sha256 ~ '^[0-9a-f]{64}$' AND report_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_search_relevance_feedback_fingerprints",
        ),
        CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array' AND jsonb_typeof(suggested_queries) = 'array'",
            name="ck_analysis_search_relevance_feedback_json_arrays",
        ),
        CheckConstraint(
            "length(btrim(patent_id)) > 0",
            name="ck_analysis_search_relevance_feedback_patent_id",
        ),
        Index(
            "ix_analysis_search_relevance_feedback_org_analysis",
            "org_id",
            "analysis_id",
        ),
        Index(
            "uq_analysis_search_relevance_feedback_reviewer_patent",
            "analysis_id",
            "patent_id",
            "reviewer_user_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    patent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relevance: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    suggested_queries: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    query_plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    reviewer_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    reviewer_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class AnalysisClaimedUseReceipt(TimestampMixin, Base):
    """Immutable counsel attestation for one report claim and proposed use.

    The signed receipt payload is retained verbatim while the surrounding row
    binds it to the exact tenant, analysis, certified report, and accused-act
    snapshot that the attorney reviewed. Revocation is append-only state; rows
    are deleted only by the explicitly authorized, audited GDPR erasure path.
    """

    __tablename__ = "analysis_claimed_use_receipts"
    __table_args__ = (
        CheckConstraint(
            "claim_number >= 1 AND accused_act_index >= 0",
            name="ck_analysis_claimed_use_receipts_positive_coordinates",
        ),
        CheckConstraint(
            "report_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND accused_act_sha256 ~ '^[0-9a-f]{64}$' "
            "AND receipt_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_claimed_use_receipts_digests",
        ),
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_by_user_id IS NULL "
            "AND revocation_reason = '') OR "
            "(revoked_at IS NOT NULL AND revoked_by_user_id IS NOT NULL "
            "AND length(btrim(revocation_reason)) >= 10)",
            name="ck_analysis_claimed_use_receipts_revocation",
        ),
        Index(
            "ix_analysis_claimed_use_receipts_org_analysis",
            "org_id",
            "analysis_id",
            "created_at",
        ),
        Index(
            "uq_analysis_claimed_use_receipts_active_subject",
            "analysis_id",
            "report_fingerprint",
            "patent_id",
            "claim_number",
            "accused_act_sha256",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_analysis_claimed_use_receipts_digest",
            "receipt_sha256",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id"),
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"),
        nullable=False,
    )
    report_id: Mapped[str] = mapped_column(String(64), nullable=False)
    report_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    patent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_number: Mapped[int] = mapped_column(nullable=False)
    accused_act_index: Mapped[int] = mapped_column(nullable=False)
    accused_act_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    issuer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    revocation_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Notification(Base):
    """In-app notification for a user."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, values_callable=lambda obj: [e.value for e in obj])
    )
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisReviewerDecision(TimestampMixin, Base):
    """Reviewer (attorney) accept / reject / edit decision on a specific finding.

    One decision per (analysis_id, finding_type, finding_ref, reviewer_user_id)
    — re-POST by the same reviewer on the same finding replaces the existing row.

    The reviewer identity is captured as the Clerk user ID plus a snapshot of
    the display name and email at decision time, so historical audit trails
    survive later user renames or role changes.
    """

    __tablename__ = "analysis_reviewer_decisions"
    __table_args__ = (
        Index("ix_decisions_analysis_org", "analysis_id", "org_id"),
        Index(
            "ix_decisions_unique_reviewer_finding",
            "analysis_id",
            "finding_type",
            "finding_ref",
            "reviewer_user_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)

    finding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    finding_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    report_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="")
    edited_text: Mapped[str] = mapped_column(Text, default="")

    reviewer_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(255), default="")
    reviewer_email: Mapped[str] = mapped_column(String(255), default="")


class AnalysisReviewStatus(TimestampMixin, Base):
    """Persisted report-level review workflow state for an analysis."""

    __tablename__ = "analysis_review_statuses"
    __table_args__ = (
        Index("ix_analysis_review_statuses_org", "org_id"),
        Index(
            "ix_analysis_review_statuses_analysis_org",
            "analysis_id",
            "org_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True, nullable=False
    )
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ReviewStatus.PENDING,
        nullable=False,
    )
    note: Mapped[str] = mapped_column(Text, default="")
    reviewer_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(255), default="")
    reviewer_email: Mapped[str] = mapped_column(String(255), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalysisCheckpointDecision(TimestampMixin, Base):
    """Persisted human decision for a pipeline checkpoint."""

    __tablename__ = "analysis_checkpoint_decisions"
    __table_args__ = (
        Index(
            "ix_analysis_checkpoint_decisions_unique",
            "analysis_id",
            "org_id",
            "checkpoint_id",
            unique=True,
        ),
        Index(
            "ix_analysis_checkpoint_decisions_org_reviewed",
            "org_id",
            "reviewed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    checkpoint_id: Mapped[str] = mapped_column(String(128), nullable=False)
    checkpoint_type: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    analysis: Mapped[Analysis] = relationship(lazy="raise")
    reviewer: Mapped[User] = relationship(lazy="raise")

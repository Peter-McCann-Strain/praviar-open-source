"""Recipient-bound external report grant ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .mixins import TimestampMixin
from .models_base import Base


class ExternalReportGrant(TimestampMixin, Base):
    """A mailbox-verified, recipient-bound grant for one completed report.

    Link and access secrets are represented only by SHA-256 digests. One-time
    verification codes use Argon2id and are never persisted in plaintext.
    """

    __tablename__ = "external_report_grants"
    __table_args__ = (
        UniqueConstraint("grant_token_hash", name="uq_external_report_grants_token_hash"),
        UniqueConstraint(
            "org_id",
            "delivery_operation_key_digest",
            name="uq_external_report_grants_org_delivery_operation",
        ),
        Index("ix_external_report_grants_org_analysis", "org_id", "analysis_id"),
        Index(
            "ix_external_report_grants_analysis_recipient",
            "analysis_id",
            "recipient_email_normalized",
        ),
        Index("ix_external_report_grants_expires", "expires_at"),
        Index(
            "ix_external_report_grants_delivery_reconcile",
            "org_id",
            "delivery_state",
            "updated_at",
        ),
        Index(
            "ix_external_report_grants_delivery_due",
            "org_id",
            "delivery_state",
            "delivery_reconciliation_next_attempt_at",
            "updated_at",
        ),
        Index(
            "uq_external_report_grants_one_unresolved_delivery",
            "org_id",
            "analysis_id",
            "recipient_email_normalized",
            unique=True,
            postgresql_where=text(
                "delivery_state IN ('prepared', 'dispatching', "
                "'provider_accepted', 'outcome_unknown')"
            ),
        ),
        CheckConstraint("max_views > 0", name="ck_external_report_grants_max_views_positive"),
        CheckConstraint(
            "view_count >= 0 AND view_count <= max_views",
            name="ck_external_report_grants_view_count_range",
        ),
        CheckConstraint(
            "max_downloads >= 0 AND download_count >= 0 AND download_count <= max_downloads",
            name="ck_external_report_grants_download_count_range",
        ),
        CheckConstraint(
            "delivery_state IN ('prepared', 'dispatching', 'provider_accepted', "
            "'active', 'rejected', 'outcome_unknown', 'cancelled')",
            name="ck_external_report_grants_delivery_state",
        ),
        CheckConstraint(
            "((delivery_state = 'active' AND invitation_sent_at IS NOT NULL) OR "
            "(delivery_state <> 'active' AND invitation_sent_at IS NULL))",
            name="ck_external_report_grants_delivery_activation",
        ),
        CheckConstraint(
            "delivery_state NOT IN ('prepared', 'dispatching', 'provider_accepted', "
            "'outcome_unknown') OR revoked_at IS NULL",
            name="ck_external_report_grants_unresolved_not_revoked",
        ),
        CheckConstraint(
            "delivery_state <> 'cancelled' OR revoked_at IS NOT NULL",
            name="ck_external_report_grants_cancelled_revoked",
        ),
        CheckConstraint(
            "delivery_terminal_reason IS NULL OR delivery_terminal_reason IN "
            "('policy', 'expired', 'retention_expired', 'user_revoked')",
            name="ck_external_report_grants_terminal_reason",
        ),
        CheckConstraint(
            "delivery_state = 'cancelled' OR delivery_terminal_reason IS NULL",
            name="ck_external_report_grants_terminal_reason_cancelled_only",
        ),
        CheckConstraint(
            "delivery_state NOT IN ('active', 'rejected', 'outcome_unknown', "
            "'cancelled') OR delivery_token_ciphertext IS NULL",
            name="ck_external_report_grants_terminal_ciphertext_cleared",
        ),
        CheckConstraint(
            "delivery_state <> 'prepared' OR delivery_token_ciphertext IS NOT NULL",
            name="ck_external_report_grants_prepared_has_ciphertext",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_domain: Mapped[str] = mapped_column(String(255), nullable=False)

    grant_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    report_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # The operation key is HMACed with a domain-separated key. The raw token is
    # held only as short-lived AES-GCM ciphertext until delivery reaches a
    # terminal state; neither value is a bearer credential on its own.
    delivery_operation_key_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_encryption_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_state: Mapped[str] = mapped_column(String(32), default="prepared")
    delivery_token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_dispatch_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_provider_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_terminal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_terminal_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_reconciliation_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_reconciliation_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    delivery_reconciliation_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invitation_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    access_secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    max_views: Mapped[int] = mapped_column(Integer, default=25)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    download_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    max_downloads: Mapped[int] = mapped_column(Integer, default=0)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

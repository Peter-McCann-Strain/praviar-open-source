"""Identity and organization ORM models."""

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .mixins import TimestampMixin
from .models_base import Base, OrgPlan, UserRole

if TYPE_CHECKING:
    from .models_analysis import Analysis, ConfigPreset
    from .models_collaboration import Comment
    from .models_operations import AuditLog


class Organization(TimestampMixin, Base):
    """Multi-tenant organization."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "external_sharing_policy_mode IN ('open', 'approved_domains_only')",
            name="ck_organizations_external_sharing_policy_mode",
        ),
        CheckConstraint(
            "external_sharing_policy_version > 0",
            name="ck_organizations_external_sharing_policy_version_positive",
        ),
        CheckConstraint(
            "(external_report_delivery_reconciliation_lease_id IS NULL) = "
            "(external_report_delivery_reconciliation_lease_expires_at IS NULL)",
            name="ck_org_external_delivery_reconcile_lease_pair",
        ),
        CheckConstraint(
            "offboarding_billing_cancellation_status IS NULL "
            "OR offboarding_billing_cancellation_status IN "
            "('pending', 'retryable', 'confirmed', 'not_required')",
            name="ck_org_offboarding_billing_status",
        ),
        CheckConstraint(
            "offboarding_billing_cancellation_attempts >= 0",
            name="ck_org_offboarding_billing_attempts_nonnegative",
        ),
        CheckConstraint(
            "(offboarding_billing_cancellation_status IN ('confirmed', 'not_required') "
            "AND offboarding_billing_confirmed_at IS NOT NULL) OR "
            "((offboarding_billing_cancellation_status IS NULL "
            "OR offboarding_billing_cancellation_status IN ('pending', 'retryable')) "
            "AND offboarding_billing_confirmed_at IS NULL)",
            name="ck_org_offboarding_billing_confirmation_shape",
        ),
        CheckConstraint(
            "offboarding_billing_cancellation_status IS NULL "
            "OR offboarding_billing_cancellation_status NOT IN ('pending', 'retryable') "
            "OR offboarding_stripe_subscription_id IS NOT NULL",
            name="ck_org_offboarding_billing_retry_locator",
        ),
        CheckConstraint(
            "offboarding_billing_cancellation_status IS NULL "
            "OR offboarding_billing_cancellation_status <> 'not_required' "
            "OR offboarding_stripe_subscription_id IS NULL",
            name="ck_org_offboarding_billing_not_required_locator",
        ),
        CheckConstraint(
            "offboarding_billing_cancellation_status IS NULL "
            "OR offboarding_billing_cancellation_status = 'not_required' "
            "OR offboarding_billing_cancellation_attempts > 0",
            name="ck_org_offboarding_billing_attempt_shape",
        ),
        CheckConstraint(
            "(offboarding_billing_cancellation_status = 'retryable' "
            "AND offboarding_billing_last_error_code IS NOT NULL) OR "
            "((offboarding_billing_cancellation_status IS NULL "
            "OR offboarding_billing_cancellation_status <> 'retryable') "
            "AND offboarding_billing_last_error_code IS NULL)",
            name="ck_org_offboarding_billing_error_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_org_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    plan: Mapped[OrgPlan] = mapped_column(
        Enum(OrgPlan, values_callable=lambda obj: [e.value for e in obj]),
        default=OrgPlan.FREE,
    )
    max_analyses_per_month: Mapped[int] = mapped_column(Integer, default=2)
    free_analyses_remaining: Mapped[int] = mapped_column(Integer, default=2)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    external_sharing_policy_mode: Mapped[str] = mapped_column(
        String(32),
        default="approved_domains_only",
        server_default="approved_domains_only",
    )
    external_sharing_approved_domains: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    external_sharing_policy_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
    )
    external_report_delivery_reconciliation_lease_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    external_report_delivery_reconciliation_lease_expires_at: Mapped[datetime | None] = (
        mapped_column(DateTime(timezone=True), nullable=True)
    )

    sso_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sso_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sso_domains: Mapped[list] = mapped_column(JSONB, default=list)
    sso_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    sso_status_available: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    sso_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sso_last_refresh_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sso_refresh_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    billing_cycle_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    analyses_used_this_month: Mapped[int] = mapped_column(Integer, default=0)

    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deletion_requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deletion_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    offboarding_billing_cancellation_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    offboarding_stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    offboarding_billing_cancellation_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    offboarding_billing_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    offboarding_billing_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    offboarding_billing_last_error_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    users: Mapped[list[User]] = relationship(lazy="raise", back_populates="organization")
    analyses: Mapped[list[Analysis]] = relationship(lazy="raise", back_populates="organization")
    config_presets: Mapped[list[ConfigPreset]] = relationship(
        lazy="raise", back_populates="organization"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(lazy="raise", back_populates="organization")


class User(Base):
    """Platform user linked to a Clerk identity and an organization."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    __table_args__ = (
        UniqueConstraint("clerk_user_id", "org_id", name="uq_users_clerk_user_org"),
        UniqueConstraint("clerk_membership_id", name="uq_users_clerk_membership_id"),
        CheckConstraint(
            "membership_deleted_at IS NULL OR NOT membership_active",
            name="ck_users_deleted_membership_inactive",
        ),
        CheckConstraint(
            "membership_permission_denied_by_operation_id IS NULL "
            "OR membership_permission_denied_at IS NOT NULL",
            name="ck_users_membership_permission_denial_owner",
        ),
        CheckConstraint(
            "membership_permission_convergence_operation_id IS NULL "
            "OR membership_permission_denied_at IS NOT NULL",
            name="ck_users_membership_permission_denial_convergence",
        ),
        CheckConstraint(
            "membership_permission_denied_by_operation_id IS NULL "
            "OR membership_permission_convergence_operation_id IS NULL",
            name="ck_users_membership_permission_denial_reference_exclusive",
        ),
        Index(
            "ix_users_membership_permission_denied_operation_id",
            "membership_permission_denied_by_operation_id",
        ),
        Index(
            "ix_users_membership_permission_convergence_operation_id",
            "membership_permission_convergence_operation_id",
        ),
    )

    clerk_user_id: Mapped[str] = mapped_column(String(255), index=True)
    clerk_membership_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clerk_membership_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, values_callable=lambda obj: [e.value for e in obj]),
        default=UserRole.SCIENTIST,
    )
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    welcome_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    membership_active: Mapped[bool] = mapped_column(Boolean, default=True)
    membership_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    membership_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    membership_permission_denied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    membership_permission_denied_by_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "clerk_admin_operations.id",
            name="fk_users_membership_permission_denied_operation",
        ),
        nullable=True,
    )
    membership_permission_convergence_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "clerk_admin_operations.id",
            name="fk_users_membership_permission_convergence_operation",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(lazy="raise", back_populates="users")
    analyses: Mapped[list[Analysis]] = relationship(
        lazy="raise", back_populates="initiated_by_user", foreign_keys="[Analysis.initiated_by]"
    )
    comments: Mapped[list[Comment]] = relationship(
        lazy="raise", back_populates="user", foreign_keys="[Comment.user_id]"
    )


class ClerkMembershipTombstone(TimestampMixin, Base):
    """Terminal deletion marker for one Clerk organization-membership ID.

    Clerk may deliver ``deleted`` before ``created`` or retry older events out
    of order. Keeping the external membership ID in a dedicated row prevents a
    late create from resurrecting a deleted authorization principal.
    """

    __tablename__ = "clerk_membership_tombstones"

    clerk_membership_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    clerk_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClerkWebhookReceipt(Base):
    """Transactional idempotency receipt for a verified Svix delivery."""

    __tablename__ = "clerk_webhook_receipts"

    svix_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClerkAdminOperation(TimestampMixin, Base):
    """Durable local authority for one buyer-initiated Clerk mutation.

    Clerk does not document idempotency guarantees for organization invitation
    or membership mutation endpoints.  Persisting the external-call boundary
    lets retries reconcile provider state without issuing the mutation twice.
    """

    __tablename__ = "clerk_admin_operations"
    __table_args__ = (
        UniqueConstraint("org_id", "client_key_digest", name="uq_clerk_admin_op_org_key"),
        CheckConstraint(
            "operation_type IN ('invite', 'role_update')",
            name="ck_clerk_admin_operations_type",
        ),
        CheckConstraint(
            "state IN ('requested', 'metadata_call_started', 'metadata_accepted', "
            "'role_call_started', 'role_accepted', 'invite_call_started', "
            "'provider_accepted', 'completed', 'failed')",
            name="ck_clerk_admin_operations_state",
        ),
        CheckConstraint(
            "(operation_type = 'role_update' AND target_user_id IS NOT NULL "
            "AND target_email_normalized IS NULL) OR "
            "(operation_type = 'invite' AND target_user_id IS NULL "
            "AND target_email_normalized IS NOT NULL)",
            name="ck_clerk_admin_operations_target_shape",
        ),
        CheckConstraint(
            "requested_role IN ('admin', 'attorney', 'scientist', 'client') "
            "AND (operation_type <> 'invite' OR requested_role <> 'admin')",
            name="ck_clerk_admin_operations_requested_role",
        ),
        Index("ix_clerk_admin_operations_org_state", "org_id", "state"),
        Index(
            "uq_clerk_admin_operations_open_role_target",
            "org_id",
            "target_user_id",
            unique=True,
            postgresql_where=text(
                "operation_type = 'role_update' AND target_user_id IS NOT NULL "
                "AND state NOT IN ('completed', 'failed')"
            ),
        ),
        Index(
            "uq_clerk_admin_operations_open_invite_email",
            "org_id",
            "target_email_normalized",
            unique=True,
            postgresql_where=text(
                "operation_type = 'invite' AND target_email_normalized IS NOT NULL "
                "AND state NOT IN ('completed', 'failed')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    initiated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    client_key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="requested")
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_email_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_role: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class APIKey(Base):
    """API key for programmatic access, scoped to an organization."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_org_revoked", "org_id", "revoked"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(128), unique=True)
    key_prefix: Mapped[str] = mapped_column(String(32))
    scopes: Mapped[list] = mapped_column(JSONB, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

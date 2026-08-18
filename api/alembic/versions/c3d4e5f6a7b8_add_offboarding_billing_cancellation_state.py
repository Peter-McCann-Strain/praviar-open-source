"""Add durable organization-offboarding billing cancellation state.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "offboarding_billing_cancellation_status",
            sa.String(32),
            nullable=True,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "offboarding_stripe_subscription_id",
            sa.String(255),
            nullable=True,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "offboarding_billing_cancellation_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "offboarding_billing_last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "offboarding_billing_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "offboarding_billing_last_error_code",
            sa.String(128),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_org_offboarding_billing_status",
        "organizations",
        "offboarding_billing_cancellation_status IS NULL "
        "OR offboarding_billing_cancellation_status IN "
        "('pending', 'retryable', 'confirmed', 'not_required')",
    )
    op.create_check_constraint(
        "ck_org_offboarding_billing_attempts_nonnegative",
        "organizations",
        "offboarding_billing_cancellation_attempts >= 0",
    )
    op.create_check_constraint(
        "ck_org_offboarding_billing_confirmation_shape",
        "organizations",
        "("
        "offboarding_billing_cancellation_status IN ('confirmed', 'not_required') "
        "AND offboarding_billing_confirmed_at IS NOT NULL"
        ") OR ("
        "("
        "offboarding_billing_cancellation_status IS NULL "
        "OR offboarding_billing_cancellation_status IN ('pending', 'retryable')"
        ") AND offboarding_billing_confirmed_at IS NULL"
        ")",
    )
    op.create_check_constraint(
        "ck_org_offboarding_billing_retry_locator",
        "organizations",
        "offboarding_billing_cancellation_status IS NULL "
        "OR offboarding_billing_cancellation_status NOT IN ('pending', 'retryable') "
        "OR offboarding_stripe_subscription_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_org_offboarding_billing_not_required_locator",
        "organizations",
        "offboarding_billing_cancellation_status IS NULL "
        "OR offboarding_billing_cancellation_status <> 'not_required' "
        "OR offboarding_stripe_subscription_id IS NULL",
    )
    op.create_check_constraint(
        "ck_org_offboarding_billing_attempt_shape",
        "organizations",
        "offboarding_billing_cancellation_status IS NULL "
        "OR offboarding_billing_cancellation_status = 'not_required' "
        "OR offboarding_billing_cancellation_attempts > 0",
    )
    op.create_check_constraint(
        "ck_org_offboarding_billing_error_shape",
        "organizations",
        "("
        "offboarding_billing_cancellation_status = 'retryable' "
        "AND offboarding_billing_last_error_code IS NOT NULL"
        ") OR ("
        "("
        "offboarding_billing_cancellation_status IS NULL "
        "OR offboarding_billing_cancellation_status <> 'retryable'"
        ") AND offboarding_billing_last_error_code IS NULL"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_org_offboarding_billing_error_shape",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_org_offboarding_billing_attempt_shape",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_org_offboarding_billing_not_required_locator",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_org_offboarding_billing_retry_locator",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_org_offboarding_billing_confirmation_shape",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_org_offboarding_billing_attempts_nonnegative",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_org_offboarding_billing_status",
        "organizations",
        type_="check",
    )
    op.drop_column("organizations", "offboarding_billing_last_error_code")
    op.drop_column("organizations", "offboarding_billing_confirmed_at")
    op.drop_column("organizations", "offboarding_billing_last_attempt_at")
    op.drop_column("organizations", "offboarding_billing_cancellation_attempts")
    op.drop_column("organizations", "offboarding_stripe_subscription_id")
    op.drop_column("organizations", "offboarding_billing_cancellation_status")

"""Add durable idempotent external report invitation delivery state.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-14 04:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "external_report_delivery_reconciliation_lease_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "external_report_delivery_reconciliation_lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_org_external_delivery_reconcile_lease_pair",
        "organizations",
        "(external_report_delivery_reconciliation_lease_id IS NULL) = "
        "(external_report_delivery_reconciliation_lease_expires_at IS NULL)",
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_operation_key_digest", sa.String(64), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_request_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_encryption_key_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_state", sa.String(32), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_token_ciphertext", sa.Text(), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_provider_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_terminal_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_terminal_reason", sa.String(32), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_provider_message_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column("delivery_reconciliation_alerted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "external_report_grants",
        sa.Column(
            "delivery_reconciliation_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "external_report_grants",
        sa.Column(
            "delivery_reconciliation_next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # This table was created with FORCE ROW LEVEL SECURITY. Production
    # migrations SET ROLE to the non-BYPASSRLS table owner, so the historical
    # data migration below would otherwise see zero rows. NO FORCE keeps RLS
    # enabled for every non-owner connection while allowing the migration owner
    # to backfill under the ACCESS EXCLUSIVE lock taken by ALTER TABLE. Alembic
    # runs this revision transactionally: any later failure rolls this change
    # back and therefore restores FORCE automatically.
    op.execute("ALTER TABLE external_report_grants NO FORCE ROW LEVEL SECURITY")

    # Historical delivered rows are active. Historical undelivered rows have
    # lost their in-memory token and are therefore terminal failures rather
    # than recoverable work.
    op.execute(
        "UPDATE external_report_grants "
        "SET delivery_state = CASE "
        "WHEN invitation_sent_at IS NOT NULL THEN 'active' ELSE 'rejected' END, "
        "delivery_terminal_at = CASE "
        "WHEN invitation_sent_at IS NULL THEN updated_at ELSE NULL END"
    )
    # SMTPUTF8 is disallowed at validation, so the mailbox is ASCII and
    # PostgreSQL lower() is equivalent to the application full-casefold key.
    # Preserve recipient_email for delivery/display while canonicalizing the
    # identity column before any recipient indexes are created.
    op.execute(
        "UPDATE external_report_grants "
        "SET recipient_email_normalized = lower(recipient_email_normalized)"
    )
    op.alter_column("external_report_grants", "delivery_state", nullable=False)
    op.create_check_constraint(
        "ck_external_report_grants_delivery_state",
        "external_report_grants",
        "delivery_state IN ('prepared', 'dispatching', 'provider_accepted', "
        "'active', 'rejected', 'outcome_unknown', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_external_report_grants_delivery_activation",
        "external_report_grants",
        "((delivery_state = 'active' AND invitation_sent_at IS NOT NULL) OR "
        "(delivery_state <> 'active' AND invitation_sent_at IS NULL))",
    )
    op.create_check_constraint(
        "ck_external_report_grants_unresolved_not_revoked",
        "external_report_grants",
        "delivery_state NOT IN ('prepared', 'dispatching', 'provider_accepted', "
        "'outcome_unknown') OR revoked_at IS NULL",
    )
    op.create_check_constraint(
        "ck_external_report_grants_cancelled_revoked",
        "external_report_grants",
        "delivery_state <> 'cancelled' OR revoked_at IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_external_report_grants_terminal_reason",
        "external_report_grants",
        "delivery_terminal_reason IS NULL OR delivery_terminal_reason IN "
        "('policy', 'expired', 'retention_expired', 'user_revoked')",
    )
    op.create_check_constraint(
        "ck_external_report_grants_terminal_reason_cancelled_only",
        "external_report_grants",
        "delivery_state = 'cancelled' OR delivery_terminal_reason IS NULL",
    )
    op.create_check_constraint(
        "ck_external_report_grants_terminal_ciphertext_cleared",
        "external_report_grants",
        "delivery_state NOT IN ('active', 'rejected', 'outcome_unknown', "
        "'cancelled') OR delivery_token_ciphertext IS NULL",
    )
    op.create_check_constraint(
        "ck_external_report_grants_prepared_has_ciphertext",
        "external_report_grants",
        "delivery_state <> 'prepared' OR delivery_token_ciphertext IS NOT NULL",
    )
    op.create_unique_constraint(
        "uq_external_report_grants_org_delivery_operation",
        "external_report_grants",
        ["org_id", "delivery_operation_key_digest"],
    )
    op.create_index(
        "ix_external_report_grants_delivery_reconcile",
        "external_report_grants",
        ["org_id", "delivery_state", "updated_at"],
    )
    op.create_index(
        "ix_external_report_grants_delivery_due",
        "external_report_grants",
        [
            "org_id",
            "delivery_state",
            "delivery_reconciliation_next_attempt_at",
            "updated_at",
        ],
    )
    op.create_index(
        "uq_external_report_grants_one_unresolved_delivery",
        "external_report_grants",
        ["org_id", "analysis_id", "recipient_email_normalized"],
        unique=True,
        postgresql_where=sa.text(
            "delivery_state IN ('prepared', 'dispatching', 'provider_accepted', 'outcome_unknown')"
        ),
    )
    op.execute("ALTER TABLE external_report_grants FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    # See upgrade(): the unresolved-work guard must run with owner visibility.
    # If it raises, PostgreSQL rolls the whole migration transaction back and
    # the pre-existing FORCE setting remains intact.
    op.execute("ALTER TABLE external_report_grants NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM external_report_grants WHERE delivery_state IN "
        "('prepared', 'dispatching', 'provider_accepted', 'outcome_unknown')) THEN "
        "RAISE EXCEPTION 'cannot downgrade with unresolved external report deliveries'; "
        "END IF; END $$"
    )
    op.drop_index(
        "uq_external_report_grants_one_unresolved_delivery",
        table_name="external_report_grants",
    )
    op.drop_index(
        "ix_external_report_grants_delivery_reconcile",
        table_name="external_report_grants",
    )
    op.drop_index(
        "ix_external_report_grants_delivery_due",
        table_name="external_report_grants",
    )
    op.drop_constraint(
        "uq_external_report_grants_org_delivery_operation",
        "external_report_grants",
        type_="unique",
    )
    op.drop_constraint(
        "ck_external_report_grants_delivery_state",
        "external_report_grants",
        type_="check",
    )
    for constraint_name in (
        "ck_external_report_grants_terminal_reason_cancelled_only",
        "ck_external_report_grants_terminal_reason",
        "ck_external_report_grants_prepared_has_ciphertext",
        "ck_external_report_grants_terminal_ciphertext_cleared",
        "ck_external_report_grants_cancelled_revoked",
        "ck_external_report_grants_unresolved_not_revoked",
        "ck_external_report_grants_delivery_activation",
    ):
        op.drop_constraint(
            constraint_name,
            "external_report_grants",
            type_="check",
        )
    op.drop_column("external_report_grants", "delivery_reconciliation_alerted_at")
    op.drop_column("external_report_grants", "delivery_reconciliation_next_attempt_at")
    op.drop_column("external_report_grants", "delivery_reconciliation_attempt_count")
    op.drop_column("external_report_grants", "delivery_provider_message_id")
    op.drop_column("external_report_grants", "delivery_terminal_reason")
    op.drop_column("external_report_grants", "delivery_terminal_at")
    op.drop_column("external_report_grants", "delivery_provider_accepted_at")
    op.drop_column("external_report_grants", "delivery_dispatch_started_at")
    op.drop_column("external_report_grants", "delivery_token_ciphertext")
    op.drop_column("external_report_grants", "delivery_state")
    op.drop_column("external_report_grants", "delivery_request_hash")
    op.drop_column("external_report_grants", "delivery_encryption_key_id")
    op.drop_column("external_report_grants", "delivery_operation_key_digest")
    op.execute("ALTER TABLE external_report_grants FORCE ROW LEVEL SECURITY")
    op.drop_constraint(
        "ck_org_external_delivery_reconcile_lease_pair",
        "organizations",
        type_="check",
    )
    op.drop_column(
        "organizations",
        "external_report_delivery_reconciliation_lease_expires_at",
    )
    op.drop_column(
        "organizations",
        "external_report_delivery_reconciliation_lease_id",
    )

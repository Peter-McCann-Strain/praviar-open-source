"""Add durable weekly digest delivery and unsubscribe capability state.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-07-17 00:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true)
            ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def upgrade() -> None:
    op.create_table(
        "weekly_digest_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            sa.String(length=32),
            nullable=False,
            server_default="prepared",
        ),
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("unsubscribe_token_digest", sa.String(length=64), nullable=True),
        sa.Column("unsubscribe_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribe_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "reconciliation_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reconciliation_next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("reconciliation_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "org_id",
            "user_id",
            "period_start",
            name="uq_weekly_digest_delivery_user_period",
        ),
        sa.UniqueConstraint(
            "submission_id",
            name="uq_weekly_digest_delivery_submission",
        ),
        sa.CheckConstraint(
            "period_end = period_start + interval '7 days'",
            name="ck_weekly_digest_delivery_period",
        ),
        sa.CheckConstraint(
            "state IN ('prepared', 'dispatching', 'outcome_unknown', "
            "'provider_accepted', 'rejected', 'cancelled')",
            name="ck_weekly_digest_delivery_state",
        ),
        sa.CheckConstraint(
            "reconciliation_attempt_count >= 0",
            name="ck_weekly_digest_delivery_reconcile_count",
        ),
        sa.CheckConstraint(
            "(unsubscribe_token_digest IS NULL) = (unsubscribe_expires_at IS NULL)",
            name="ck_weekly_digest_delivery_token_pair",
        ),
        sa.CheckConstraint(
            "unsubscribe_used_at IS NULL OR unsubscribe_token_digest IS NOT NULL",
            name="ck_weekly_digest_delivery_token_use",
        ),
        sa.CheckConstraint(
            "(state = 'prepared' AND provider_attempt_started_at IS NULL "
            "AND recipient_email IS NULL AND unsubscribe_token_digest IS NULL) OR "
            "(state <> 'prepared' AND "
            "(state = 'cancelled' OR provider_attempt_started_at IS NOT NULL))",
            name="ck_weekly_digest_delivery_attempt_boundary",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "(state = 'provider_accepted' AND provider_message_id IS NOT NULL "
            "AND provider_accepted_at IS NOT NULL) OR "
            "(state <> 'provider_accepted' AND provider_message_id IS NULL "
            "AND provider_accepted_at IS NULL)",
            name="ck_weekly_digest_delivery_provider_acceptance",
        ),
        sa.CheckConstraint(
            "(state IN ('rejected', 'cancelled') AND terminal_at IS NOT NULL) OR "
            "(state NOT IN ('rejected', 'cancelled') AND terminal_at IS NULL)",
            name="ck_weekly_digest_delivery_terminal",
        ),
    )
    op.create_index(
        "ix_weekly_digest_deliveries_org_due",
        "weekly_digest_deliveries",
        ["org_id", "state", "reconciliation_next_attempt_at"],
    )
    op.create_index(
        "ix_weekly_digest_deliveries_org_period",
        "weekly_digest_deliveries",
        ["org_id", "period_start", "user_id"],
    )
    op.create_index(
        "uq_weekly_digest_deliveries_token_digest",
        "weekly_digest_deliveries",
        ["unsubscribe_token_digest"],
        unique=True,
        postgresql_where=sa.text("unsubscribe_token_digest IS NOT NULL"),
    )

    # A globally unique user id is not sufficient evidence that the delivery's
    # copied org_id is the same tenant as the user. Enforce that relationship at
    # the database boundary so BYPASSRLS workers cannot create cross-org rows.
    op.execute(
        """
        CREATE FUNCTION validate_weekly_digest_delivery_org()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM users
                WHERE id = NEW.user_id
                  AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION
                    'weekly digest delivery user must belong to the same organization';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_weekly_digest_delivery_org
        BEFORE INSERT OR UPDATE OF org_id, user_id
        ON weekly_digest_deliveries
        FOR EACH ROW
        EXECUTE FUNCTION validate_weekly_digest_delivery_org()
        """
    )

    op.execute("ALTER TABLE weekly_digest_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE weekly_digest_deliveries FORCE ROW LEVEL SECURITY")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON weekly_digest_deliveries
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR})
        """
    )
    # Public unsubscribe requests bind only the keyed capability digest. The
    # application learns org_id/user_id from the exact matching row, then binds
    # app.current_org_id before any update or user-table access.
    op.execute(
        """
        CREATE POLICY weekly_digest_unsubscribe_lookup
        ON weekly_digest_deliveries
        FOR SELECT
        USING (
            unsubscribe_token_digest IS NOT NULL
            AND unsubscribe_token_digest =
                current_setting('app.digest_unsubscribe_token_digest', true)
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE weekly_digest_deliveries NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM weekly_digest_deliveries
                WHERE state IN ('dispatching', 'outcome_unknown')
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade with unresolved weekly digest deliveries';
            END IF;
        END
        $$;
        """
    )
    op.execute("DROP POLICY IF EXISTS weekly_digest_unsubscribe_lookup ON weekly_digest_deliveries")
    op.execute("DROP POLICY IF EXISTS org_isolation ON weekly_digest_deliveries")
    op.execute("DROP TRIGGER IF EXISTS trg_weekly_digest_delivery_org ON weekly_digest_deliveries")
    op.execute("DROP FUNCTION IF EXISTS validate_weekly_digest_delivery_org()")
    op.drop_index(
        "uq_weekly_digest_deliveries_token_digest",
        table_name="weekly_digest_deliveries",
    )
    op.drop_index(
        "ix_weekly_digest_deliveries_org_period",
        table_name="weekly_digest_deliveries",
    )
    op.drop_index(
        "ix_weekly_digest_deliveries_org_due",
        table_name="weekly_digest_deliveries",
    )
    op.drop_table("weekly_digest_deliveries")

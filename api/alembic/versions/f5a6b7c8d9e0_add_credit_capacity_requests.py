"""Add durable Report Credit capacity requests and tenant isolation.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-16 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | Sequence[str] | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CONTEXT_UUID_EXPR = """
CASE
    WHEN current_setting('app.current_org_id', true)
        ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    THEN current_setting('app.current_org_id', true)::uuid
    ELSE NULL::uuid
END
"""


def upgrade() -> None:
    op.create_table(
        "credit_capacity_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requester_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requester_name", sa.String(255), nullable=False),
        sa.Column("requested_reports", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("notified_admins", sa.Integer(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "fulfillment_credit_ledger_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_credit_ledger.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "requested_reports BETWEEN 1 AND 30",
            name="ck_credit_capacity_requests_reports",
        ),
        sa.CheckConstraint(
            "source IN ('analysis_launch', 'capacity_watch', 'launch_retry')",
            name="ck_credit_capacity_requests_source",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'fulfilled', 'declined')",
            name="ck_credit_capacity_requests_status",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "resolution_note IS NULL OR char_length(resolution_note) <= 1000",
            name="ck_credit_capacity_requests_note_length",
        ),
        sa.CheckConstraint(
            "status != 'declined' OR "
            "(resolution_note IS NOT NULL "
            "AND char_length(btrim(resolution_note)) >= 4)",
            name="ck_credit_capacity_requests_decline_reason",
        ),
        sa.CheckConstraint(
            "notified_admins > 0",
            name="ck_credit_capacity_requests_notified_admins",
        ),
    )
    op.create_index(
        "ix_credit_capacity_requests_org_status_requested",
        "credit_capacity_requests",
        ["org_id", "status", "requested_at", "id"],
    )
    op.create_index(
        "ix_credit_capacity_requests_requester_requested",
        "credit_capacity_requests",
        ["org_id", "requester_user_id", "requested_at"],
    )
    op.create_index(
        "ix_credit_capacity_requests_fulfillment_ledger",
        "credit_capacity_requests",
        ["fulfillment_credit_ledger_id"],
    )
    op.execute("ALTER TABLE credit_capacity_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE credit_capacity_requests FORCE ROW LEVEL SECURITY")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON credit_capacity_requests
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.validate_credit_capacity_request_org()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NEW.requester_user_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.users
                WHERE id = NEW.requester_user_id AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION
                    'credit capacity requester belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.resolved_by_user_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.users
                WHERE id = NEW.resolved_by_user_id AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION
                    'credit capacity resolver belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.fulfillment_credit_ledger_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.analysis_credit_ledger
                WHERE id = NEW.fulfillment_credit_ledger_id
                  AND org_id = NEW.org_id
                  AND kind = 'purchase'
            ) THEN
                RAISE EXCEPTION
                    'credit capacity fulfillment ledger belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_credit_capacity_request_org_guard
            BEFORE INSERT OR UPDATE ON credit_capacity_requests
            FOR EACH ROW
            EXECUTE FUNCTION public.validate_credit_capacity_request_org();
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE credit_capacity_requests NO FORCE ROW LEVEL SECURITY")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM credit_capacity_requests) THEN
                    EXECUTE
                        'ALTER TABLE credit_capacity_requests FORCE ROW LEVEL SECURITY';
                    RAISE EXCEPTION
                        'Refusing to downgrade while credit capacity requests remain';
                END IF;
            EXCEPTION WHEN OTHERS THEN
                EXECUTE
                    'ALTER TABLE credit_capacity_requests FORCE ROW LEVEL SECURITY';
                RAISE;
            END
            $$;
            """
        )
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_credit_capacity_request_org_guard ON credit_capacity_requests"
    )
    op.execute("DROP FUNCTION IF EXISTS public.validate_credit_capacity_request_org()")
    op.execute("DROP POLICY IF EXISTS org_isolation ON credit_capacity_requests")
    op.execute("ALTER TABLE credit_capacity_requests DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_credit_capacity_requests_fulfillment_ledger",
        table_name="credit_capacity_requests",
    )
    op.drop_index(
        "ix_credit_capacity_requests_requester_requested",
        table_name="credit_capacity_requests",
    )
    op.drop_index(
        "ix_credit_capacity_requests_org_status_requested",
        table_name="credit_capacity_requests",
    )
    op.drop_table("credit_capacity_requests")

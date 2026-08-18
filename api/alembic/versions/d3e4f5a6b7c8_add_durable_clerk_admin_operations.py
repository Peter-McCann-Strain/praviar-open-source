"""Add durable Clerk admin mutation operations and permission deny marker.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-14 06:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_POLICY = """
CREATE POLICY org_isolation ON clerk_admin_operations
    FOR ALL
    USING (
        org_id = CASE
            WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            THEN current_setting('app.current_org_id', true)::uuid
            ELSE NULL::uuid
        END
    )
    WITH CHECK (
        org_id = CASE
            WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            THEN current_setting('app.current_org_id', true)::uuid
            ELSE NULL::uuid
        END
    )
"""


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("membership_permission_denied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "clerk_admin_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "initiated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("client_key_digest", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("target_email_normalized", sa.String(255), nullable=True),
        sa.Column("requested_role", sa.String(32), nullable=False),
        sa.Column("provider_resource_id", sa.String(255), nullable=True),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
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
            "operation_type IN ('invite', 'role_update')",
            name="ck_clerk_admin_operations_type",
        ),
        sa.CheckConstraint(
            "state IN ('requested', 'metadata_call_started', 'metadata_accepted', "
            "'role_call_started', 'role_accepted', 'invite_call_started', "
            "'provider_accepted', 'completed', 'failed')",
            name="ck_clerk_admin_operations_state",
        ),
        sa.CheckConstraint(
            "(operation_type = 'role_update' AND target_user_id IS NOT NULL "
            "AND target_email_normalized IS NULL) OR "
            "(operation_type = 'invite' AND target_user_id IS NULL "
            "AND target_email_normalized IS NOT NULL)",
            name="ck_clerk_admin_operations_target_shape",
        ),
        sa.CheckConstraint(
            "requested_role IN ('admin', 'attorney', 'scientist', 'client') "
            "AND (operation_type <> 'invite' OR requested_role <> 'admin')",
            name="ck_clerk_admin_operations_requested_role",
        ),
        sa.UniqueConstraint("org_id", "client_key_digest", name="uq_clerk_admin_op_org_key"),
    )
    op.add_column(
        "users",
        sa.Column(
            "membership_permission_denied_by_operation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "membership_permission_convergence_operation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_users_membership_permission_denied_operation",
        "users",
        "clerk_admin_operations",
        ["membership_permission_denied_by_operation_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_users_membership_permission_convergence_operation",
        "users",
        "clerk_admin_operations",
        ["membership_permission_convergence_operation_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_users_membership_permission_denial_owner",
        "users",
        "membership_permission_denied_by_operation_id IS NULL "
        "OR membership_permission_denied_at IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_users_membership_permission_denial_convergence",
        "users",
        "membership_permission_convergence_operation_id IS NULL "
        "OR membership_permission_denied_at IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_users_membership_permission_denial_reference_exclusive",
        "users",
        "membership_permission_denied_by_operation_id IS NULL "
        "OR membership_permission_convergence_operation_id IS NULL",
    )
    op.create_index(
        "ix_users_membership_permission_denied_operation_id",
        "users",
        ["membership_permission_denied_by_operation_id"],
    )
    op.create_index(
        "ix_users_membership_permission_convergence_operation_id",
        "users",
        ["membership_permission_convergence_operation_id"],
    )
    op.create_index(
        "ix_clerk_admin_operations_org_state",
        "clerk_admin_operations",
        ["org_id", "state"],
    )
    op.create_index(
        "uq_clerk_admin_operations_open_role_target",
        "clerk_admin_operations",
        ["org_id", "target_user_id"],
        unique=True,
        postgresql_where=sa.text(
            "operation_type = 'role_update' AND target_user_id IS NOT NULL "
            "AND state NOT IN ('completed', 'failed')"
        ),
    )
    op.create_index(
        "uq_clerk_admin_operations_open_invite_email",
        "clerk_admin_operations",
        ["org_id", "target_email_normalized"],
        unique=True,
        postgresql_where=sa.text(
            "operation_type = 'invite' AND target_email_normalized IS NOT NULL "
            "AND state NOT IN ('completed', 'failed')"
        ),
    )
    op.execute("ALTER TABLE clerk_admin_operations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE clerk_admin_operations FORCE ROW LEVEL SECURITY")
    op.execute(_RLS_POLICY)


def downgrade() -> None:
    # FORCE must be lifted temporarily so the migration owner can inspect all
    # tenant rows. Keep RLS and its policy enabled until the destructive guard
    # passes. On any guard/query failure, restore FORCE explicitly before
    # aborting; the surrounding Alembic transaction is an additional backstop.
    op.execute("ALTER TABLE clerk_admin_operations NO FORCE ROW LEVEL SECURITY")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM clerk_admin_operations
                    WHERE state NOT IN ('completed', 'failed')
                ) OR EXISTS (
                    SELECT 1
                    FROM users
                    WHERE membership_permission_denied_at IS NOT NULL
                       OR membership_permission_denied_by_operation_id IS NOT NULL
                       OR membership_permission_convergence_operation_id IS NOT NULL
                ) THEN
                    EXECUTE 'ALTER TABLE clerk_admin_operations FORCE ROW LEVEL SECURITY';
                    RAISE EXCEPTION
                        'Refusing to downgrade while Clerk admin operations or membership denial/convergence markers remain';
                END IF;
            EXCEPTION WHEN OTHERS THEN
                EXECUTE 'ALTER TABLE clerk_admin_operations FORCE ROW LEVEL SECURITY';
                RAISE;
            END
            $$
            """
        )
    )

    op.execute("DROP POLICY IF EXISTS org_isolation ON clerk_admin_operations")
    op.execute("ALTER TABLE clerk_admin_operations DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "uq_clerk_admin_operations_open_invite_email",
        table_name="clerk_admin_operations",
    )
    op.drop_index(
        "uq_clerk_admin_operations_open_role_target",
        table_name="clerk_admin_operations",
    )
    op.drop_index("ix_clerk_admin_operations_org_state", table_name="clerk_admin_operations")
    op.drop_constraint(
        "ck_users_membership_permission_denial_reference_exclusive",
        "users",
        type_="check",
    )
    op.drop_constraint(
        "ck_users_membership_permission_denial_convergence",
        "users",
        type_="check",
    )
    op.drop_constraint(
        "ck_users_membership_permission_denial_owner",
        "users",
        type_="check",
    )
    op.drop_index(
        "ix_users_membership_permission_convergence_operation_id",
        table_name="users",
    )
    op.drop_index(
        "ix_users_membership_permission_denied_operation_id",
        table_name="users",
    )
    op.drop_constraint(
        "fk_users_membership_permission_convergence_operation",
        "users",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_users_membership_permission_denied_operation",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "membership_permission_convergence_operation_id")
    op.drop_column("users", "membership_permission_denied_by_operation_id")
    op.drop_table("clerk_admin_operations")
    op.drop_column("users", "membership_permission_denied_at")

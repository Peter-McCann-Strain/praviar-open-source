"""Persist Clerk organization memberships as per-tenant principals.

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-07-14 01:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "z0a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "y9z0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def upgrade() -> None:
    # ``users`` is the local per-organization authorization principal. Existing
    # rows remain active so the migration does not revoke established tenants;
    # new B2B rows are created only from verified membership events.
    op.drop_constraint("users_clerk_user_id_key", "users", type_="unique")
    op.add_column(
        "users",
        sa.Column("clerk_membership_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("clerk_membership_role", sa.String(32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "membership_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "membership_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("membership_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET membership_updated_at = created_at")
    op.alter_column(
        "users",
        "membership_updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    op.create_unique_constraint(
        "uq_users_clerk_user_org",
        "users",
        ["clerk_user_id", "org_id"],
    )
    op.create_unique_constraint(
        "uq_users_clerk_membership_id",
        "users",
        ["clerk_membership_id"],
    )

    op.create_table(
        "clerk_membership_tombstones",
        sa.Column("clerk_membership_id", sa.String(255), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clerk_user_id", sa.String(255), nullable=True),
        sa.Column("event_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_clerk_membership_tombstones_org",
        "clerk_membership_tombstones",
        ["org_id"],
    )
    op.execute("ALTER TABLE clerk_membership_tombstones ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE clerk_membership_tombstones FORCE ROW LEVEL SECURITY")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON clerk_membership_tombstones
        FOR ALL
        USING (org_id = {ORG_CONTEXT_UUID_EXPR})
        WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR})
        """
    )

    # This table is deliberately global: receipt claiming happens immediately
    # after Svix verification, before an organization can be trusted or bound.
    op.create_table(
        "clerk_webhook_receipts",
        sa.Column("svix_id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(payload_sha256) = 64",
            name="ck_clerk_webhook_receipts_payload_sha256_length",
        ),
    )


def downgrade() -> None:
    op.drop_table("clerk_webhook_receipts")
    op.drop_table("clerk_membership_tombstones")
    op.drop_constraint("uq_users_clerk_membership_id", "users", type_="unique")
    op.drop_constraint("uq_users_clerk_user_org", "users", type_="unique")
    op.drop_column("users", "membership_deleted_at")
    op.drop_column("users", "membership_updated_at")
    op.drop_column("users", "membership_active")
    op.drop_column("users", "clerk_membership_role")
    op.drop_column("users", "clerk_membership_id")
    # Downgrade intentionally fails if one Clerk identity now belongs to more
    # than one org; silently deleting principals would be unsafe.
    op.create_unique_constraint("users_clerk_user_id_key", "users", ["clerk_user_id"])

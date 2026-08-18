"""Add API key scopes and expiry.

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-07-02 20:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "v6w7x8y9z0a1"
down_revision: str | Sequence[str] | None = "u5v6w7x8y9z0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def _apply_api_key_policy() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON api_keys;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON api_keys
            FOR SELECT
            USING (
                org_id = {ORG_CONTEXT_UUID_EXPR}
                OR (
                    current_setting('app.api_key_prefix', true) <> ''
                    AND key_prefix = current_setting('app.api_key_prefix', true)
                )
            );
        """
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_write_isolation ON api_keys
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text('\'["analyses:read", "reports:read"]\'::jsonb'),
            nullable=False,
        ),
    )
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE api_keys
        SET expires_at = GREATEST(
            created_at + INTERVAL '90 days',
            now() + INTERVAL '30 days'
        )
        WHERE expires_at IS NULL
        """
    )
    op.alter_column(
        "api_keys",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "api_keys",
        "scopes",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        server_default=None,
        existing_nullable=False,
    )
    op.create_index("ix_api_keys_org_expires_at", "api_keys", ["org_id", "expires_at"])
    op.create_index("ix_api_keys_prefix_active", "api_keys", ["key_prefix", "revoked"])
    _apply_api_key_policy()


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_write_isolation ON api_keys;")
    op.execute("DROP POLICY IF EXISTS org_isolation ON api_keys;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON api_keys
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.drop_index("ix_api_keys_prefix_active", table_name="api_keys")
    op.drop_index("ix_api_keys_org_expires_at", table_name="api_keys")
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "scopes")

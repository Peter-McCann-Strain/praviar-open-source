"""Add analysis credit ledger for pay-as-you-go packs.

Revision ID: t4u5v6w7x8y9
Revises: s3n4o5p6q7r8
Create Date: 2026-06-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "t4u5v6w7x8y9"
down_revision: str | Sequence[str] | None = "s3n4o5p6q7r8"
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
    op.create_table(
        "analysis_credit_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("credits_delta", sa.Integer(), nullable=False),
        sa.Column("credit_pack_id", sa.String(length=64), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "stripe_checkout_session_id",
            name="uq_analysis_credit_ledger_stripe_session",
        ),
    )
    op.create_index(
        "ix_analysis_credit_ledger_org_created",
        "analysis_credit_ledger",
        ["org_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_credit_ledger_org_kind",
        "analysis_credit_ledger",
        ["org_id", "kind"],
    )
    op.execute("ALTER TABLE analysis_credit_ledger ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE analysis_credit_ledger FORCE ROW LEVEL SECURITY;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON analysis_credit_ledger
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON analysis_credit_ledger;")
    op.execute("ALTER TABLE analysis_credit_ledger NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE analysis_credit_ledger DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_analysis_credit_ledger_org_kind", table_name="analysis_credit_ledger")
    op.drop_index("ix_analysis_credit_ledger_org_created", table_name="analysis_credit_ledger")
    op.drop_table("analysis_credit_ledger")

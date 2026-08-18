"""Add persisted checkpoint decisions.

Revision ID: 9d4e2f6a1b3c
Revises: 6c1e9a4b7d2f
Create Date: 2026-06-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9d4e2f6a1b3c"
down_revision: str | Sequence[str] | None = "6c1e9a4b7d2f"
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
        "analysis_checkpoint_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("checkpoint_id", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_type", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
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
    )
    op.create_index(
        "ix_analysis_checkpoint_decisions_unique",
        "analysis_checkpoint_decisions",
        ["analysis_id", "org_id", "checkpoint_id"],
        unique=True,
    )
    op.create_index(
        "ix_analysis_checkpoint_decisions_org_reviewed",
        "analysis_checkpoint_decisions",
        ["org_id", "reviewed_at"],
    )
    op.execute("ALTER TABLE analysis_checkpoint_decisions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE analysis_checkpoint_decisions FORCE ROW LEVEL SECURITY;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON analysis_checkpoint_decisions
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON analysis_checkpoint_decisions;")
    op.drop_index(
        "ix_analysis_checkpoint_decisions_org_reviewed",
        table_name="analysis_checkpoint_decisions",
    )
    op.drop_index(
        "ix_analysis_checkpoint_decisions_unique",
        table_name="analysis_checkpoint_decisions",
    )
    op.drop_table("analysis_checkpoint_decisions")

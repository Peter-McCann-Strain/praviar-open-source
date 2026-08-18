"""Add direct org_id isolation to comments.

Revision ID: 4b8c6d2e9f10
Revises: 8a6b4d2c9e1f
Create Date: 2026-06-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4b8c6d2e9f10"
down_revision: str | Sequence[str] | None = "8a6b4d2c9e1f"
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
    op.add_column("comments", sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE comments
           SET org_id = analyses.org_id
          FROM analyses
         WHERE comments.analysis_id = analyses.id
           AND comments.org_id IS NULL;
        """
    )
    op.alter_column("comments", "org_id", nullable=False)
    op.create_foreign_key(
        "fk_comments_org_id_organizations",
        "comments",
        "organizations",
        ["org_id"],
        ["id"],
    )
    op.create_index(
        "ix_comments_org_analysis_created",
        "comments",
        ["org_id", "analysis_id", "created_at"],
    )
    op.execute("ALTER TABLE comments ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE comments FORCE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS org_isolation ON comments;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON comments
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON comments;")
    op.execute("ALTER TABLE comments NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE comments DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_comments_org_analysis_created", table_name="comments")
    op.drop_constraint("fk_comments_org_id_organizations", "comments", type_="foreignkey")
    op.drop_column("comments", "org_id")

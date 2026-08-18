"""Add org_id to attorney_feedback and enable RLS.

Revision ID: k5f6a7b8c9d0
Revises: j4e5f6a7b8c9
Create Date: 2026-06-13 00:00:00.000000

Upgrades attorney_feedback from indirect (FK-chain) tenant isolation to direct
org_id isolation with a standard org_isolation RLS policy, matching the pattern
established by comments, comment_assignment_events, and related tables.

The org_id column is backfilled via JOIN to analyses so existing rows are
correctly assigned before the NOT NULL constraint is applied.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "k5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "j4e5f6a7b8c9"
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
    op.add_column(
        "attorney_feedback",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE attorney_feedback
        SET org_id = analyses.org_id
        FROM analyses
        WHERE attorney_feedback.analysis_id = analyses.id
        """
    )
    op.alter_column("attorney_feedback", "org_id", nullable=False)
    op.create_index(
        "ix_attorney_feedback_org_id",
        "attorney_feedback",
        ["org_id"],
    )
    op.create_foreign_key(
        "fk_attorney_feedback_org_id",
        "attorney_feedback",
        "organizations",
        ["org_id"],
        ["id"],
    )

    # Table identifier is a static literal. PostgreSQL DDL identifiers cannot be bound params.
    op.execute(
        "ALTER TABLE attorney_feedback ENABLE ROW LEVEL SECURITY;"
    )  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    op.execute(
        "ALTER TABLE attorney_feedback FORCE ROW LEVEL SECURITY;"
    )  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    op.execute(
        "DROP POLICY IF EXISTS org_isolation ON attorney_feedback;"
    )  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON attorney_feedback
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS org_isolation ON attorney_feedback;"
    )  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    op.execute(
        "ALTER TABLE attorney_feedback NO FORCE ROW LEVEL SECURITY;"
    )  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    op.execute(
        "ALTER TABLE attorney_feedback DISABLE ROW LEVEL SECURITY;"
    )  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    op.drop_constraint("fk_attorney_feedback_org_id", "attorney_feedback", type_="foreignkey")
    op.drop_index("ix_attorney_feedback_org_id", table_name="attorney_feedback")
    op.drop_column("attorney_feedback", "org_id")

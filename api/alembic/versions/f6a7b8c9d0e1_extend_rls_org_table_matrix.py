"""Extend RLS to every direct org_id runtime table.

Revision ID: f6a7b8c9d0e1
Revises: 0043_indexes_cascades, e9f4a2b7c3d5
Create Date: 2026-05-25 00:00:00.000000

This closes the RLS matrix gap for direct ``org_id`` tables introduced after
the original RLS migration. ``users`` remains the explicit bootstrap exception
because Clerk user lookup happens before org context is available.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = (
    "0043_indexes_cascades",
    "e9f4a2b7c3d5",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ORG_SCOPED_TABLES: tuple[str, ...] = (
    "analysis_review_statuses",
    "comment_assignment_events",
    "comment_thread_escalations",
    "config_presets",
    "stripe_events",
)

ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def upgrade() -> None:
    for table in ORG_SCOPED_TABLES:
        # Table identifiers are static, reviewed allowlist entries from
        # ORG_SCOPED_TABLES. PostgreSQL DDL identifiers cannot be bound params.
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"
        )
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"
        )
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"DROP POLICY IF EXISTS org_isolation ON {table};"
        )
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"""
            CREATE POLICY org_isolation ON {table}
                FOR ALL
                USING (org_id = {ORG_CONTEXT_UUID_EXPR})
                WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
            """
        )


def downgrade() -> None:
    for table in ORG_SCOPED_TABLES:
        # Table identifiers are static, reviewed allowlist entries from
        # ORG_SCOPED_TABLES. PostgreSQL DDL identifiers cannot be bound params.
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"DROP POLICY IF EXISTS org_isolation ON {table};"
        )
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;"
        )
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )

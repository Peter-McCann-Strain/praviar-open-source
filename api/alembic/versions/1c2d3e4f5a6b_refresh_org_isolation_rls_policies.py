"""Refresh org_isolation RLS policies with malformed-context-safe casts.

Revision ID: 1c2d3e4f5a6b
Revises: 0a1b2c3d4e6f
Create Date: 2026-06-01 00:00:00.000000

Historical migrations now define the canonical policy for fresh databases, but
already-migrated staging and production databases need a forward migration to
replace the deployed policies in place.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "1c2d3e4f5a6b"
down_revision: str | Sequence[str] | None = "0a1b2c3d4e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ORG_SCOPED_TABLES: tuple[str, ...] = (
    "analyses",
    "analysis_review_statuses",
    "analysis_reviewer_decisions",
    "api_keys",
    "audit_logs",
    "batch_analyses",
    "comment_assignment_events",
    "comment_thread_escalations",
    "config_presets",
    "export_jobs",
    "faithfulness_scores",
    "monitors",
    "notifications",
    "stripe_events",
)

ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def _apply_org_isolation_policy(table: str) -> None:
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


def upgrade() -> None:
    for table in ORG_SCOPED_TABLES:
        _apply_org_isolation_policy(table)

    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        """
        COMMENT ON POLICY org_isolation ON audit_logs IS
            'Row-level isolation by org_id. Enforced via app.current_org_id session setting. '
            'Missing or malformed tenant context resolves to no visible rows.';
        """
    )


def downgrade() -> None:
    # Do not recreate the historical unsafe cast policy on downgrade. Keeping
    # the malformed-context-safe policy is the only fail-closed tenant boundary.
    for table in ORG_SCOPED_TABLES:
        _apply_org_isolation_policy(table)

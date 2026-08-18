"""Enable PostgreSQL Row-Level Security on all org-scoped tables.

Revision ID: a1b2c3d4e5f6
Revises: f4c8a2d6b9e1
Create Date: 2026-05-15 00:00:00.000000

RLS is the defense-in-depth layer against accidental cross-tenant data leakage.
Application code already filters by `org_id`; this migration enforces the same
guarantee at the database level so a missing WHERE clause cannot leak data.

Mechanism:
    1. ENABLE ROW LEVEL SECURITY on each org-scoped table.
    2. CREATE POLICY org_isolation that restricts visible rows to those whose
       `org_id` matches the per-session setting `app.current_org_id`.
    3. The runtime application user `praviar` is NOT the table owner, so RLS
       applies to it. The alembic migration user IS the owner (or has BYPASSRLS)
       so migrations and admin tasks continue to work.
    4. `api/src/api/db/session.py` is responsible for setting
       `SET LOCAL app.current_org_id = <org_id>` per request, immediately after
       Clerk middleware resolves the org.

`current_setting('app.current_org_id', true)` returns NULL or an empty string
when unset/reset depending on PostgreSQL session state. The policy first checks
that the setting is UUID-shaped before casting it, so missing or malformed
tenant context sees zero rows rather than crashing. This is the intended safe
default.

At the time of this migration, the tables protected are the 8 org-scoped tables
that carried a direct `org_id` column:
    analyses, audit_logs, notifications, monitors, batch_analyses,
    analysis_reviewer_decisions, api_keys, export_jobs
Tables scoped indirectly through analysis_id (comments, attorney_feedback) are
excluded; they are isolated at the application layer through the FK chain.

Note that the canonical `organizations` table itself is NOT protected by this
migration — the application uses `organizations.id` to bootstrap session
context. Access to `organizations` is governed by Clerk-level auth, not RLS.
The `users` table is similarly not RLS-protected (lookup by Clerk user_id
before org context exists).

Later direct-org tables are covered by follow-up RLS migrations and by the
model-introspection matrix in ``api/tests/test_multitenant_isolation.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f4c8a2d6b9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables that have a direct `org_id` column and require RLS isolation.
# Excluded (indirect FK chain through analysis_id, no direct org_id):
#   comments          → scoped via analysis_id → analyses.org_id
#   attorney_feedback → scoped via analysis_id → analyses.org_id
ORG_SCOPED_TABLES: tuple[str, ...] = (
    "analyses",
    "audit_logs",
    "notifications",
    "monitors",
    "batch_analyses",
    "analysis_reviewer_decisions",
    "api_keys",
    "export_jobs",
)

ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def upgrade() -> None:
    op.add_column(
        "export_jobs",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE export_jobs
        SET org_id = analyses.org_id
        FROM analyses
        WHERE export_jobs.analysis_id = analyses.id
        """
    )
    op.alter_column("export_jobs", "org_id", nullable=False)
    op.create_index(
        "ix_export_jobs_org_status",
        "export_jobs",
        ["org_id", "status"],
    )

    for table in ORG_SCOPED_TABLES:
        # Table identifiers are static, reviewed allowlist entries from
        # ORG_SCOPED_TABLES. PostgreSQL DDL identifiers cannot be bound params.
        # Enable RLS on the table.
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"
        )

        # Force RLS even for the table owner (so admin tools accidentally running
        # as owner don't bypass isolation). Owners can still bypass by holding
        # the BYPASSRLS attribute on the role itself.
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"
        )

        # Drop pre-existing policy if any (idempotency for re-applies on staging).
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"DROP POLICY IF EXISTS org_isolation ON {table};"
        )

        # Create the canonical org-isolation policy.
        # USING clause restricts row visibility for SELECT/UPDATE/DELETE.
        # WITH CHECK clause prevents writing rows for a different org_id on INSERT/UPDATE.
        # Missing or malformed tenant context resolves to NULL before the cast,
        # so unauthenticated sessions see no rows instead of raising.
        op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            f"""
            CREATE POLICY org_isolation ON {table}
                FOR ALL
                USING (org_id = {ORG_CONTEXT_UUID_EXPR})
                WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
            """
        )

    # Document the application invariant in the audit_logs table for SOC 2 evidence.
    op.execute(
        """
        COMMENT ON POLICY org_isolation ON audit_logs IS
            'Row-level isolation by org_id. Enforced via `app.current_org_id` session setting '
            'in api/src/api/db/session.py. Bypass requires BYPASSRLS role attribute.';
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
    op.drop_index("ix_export_jobs_org_status", table_name="export_jobs")
    op.drop_column("export_jobs", "org_id")

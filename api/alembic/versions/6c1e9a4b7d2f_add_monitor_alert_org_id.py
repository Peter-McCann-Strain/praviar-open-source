"""Add direct org_id isolation to monitor alerts.

Revision ID: 6c1e9a4b7d2f
Revises: 4b8c6d2e9f10
Create Date: 2026-06-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6c1e9a4b7d2f"
down_revision: str | Sequence[str] | None = "4b8c6d2e9f10"
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
        "monitor_alerts",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE monitor_alerts
           SET org_id = monitors.org_id
          FROM monitors
         WHERE monitor_alerts.monitor_id = monitors.id
           AND monitor_alerts.org_id IS NULL;
        """
    )
    op.alter_column("monitor_alerts", "org_id", nullable=False)
    op.create_foreign_key(
        "fk_monitor_alerts_org_id_organizations",
        "monitor_alerts",
        "organizations",
        ["org_id"],
        ["id"],
    )
    op.create_index(
        "ix_monitor_alerts_org_created",
        "monitor_alerts",
        ["org_id", "created_at"],
    )
    op.execute("ALTER TABLE monitor_alerts ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE monitor_alerts FORCE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS org_isolation ON monitor_alerts;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON monitor_alerts
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON monitor_alerts;")
    op.execute("ALTER TABLE monitor_alerts NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE monitor_alerts DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_monitor_alerts_org_created", table_name="monitor_alerts")
    op.drop_constraint(
        "fk_monitor_alerts_org_id_organizations",
        "monitor_alerts",
        type_="foreignkey",
    )
    op.drop_column("monitor_alerts", "org_id")

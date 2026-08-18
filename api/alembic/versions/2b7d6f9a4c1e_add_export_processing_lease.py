"""Add export processing lease for idempotent worker retries.

Revision ID: 2b7d6f9a4c1e
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-02 00:00:00.000000

Cloud Tasks and Celery can redeliver export jobs. The nullable lease lets the
worker skip active duplicate deliveries while reclaiming processing rows that
were stranded by a worker crash or timeout.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2b7d6f9a4c1e"
down_revision: str | Sequence[str] | None = "1c2d3e4f5a6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "export_jobs",
        sa.Column("retry_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "export_jobs",
        sa.Column("processing_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "export_jobs",
        sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_export_jobs_processing_lease",
        "export_jobs",
        ["status", "processing_lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_processing_lease", table_name="export_jobs")
    op.drop_column("export_jobs", "processing_lease_expires_at")
    op.drop_column("export_jobs", "processing_execution_id")
    op.drop_column("export_jobs", "retry_attempts")

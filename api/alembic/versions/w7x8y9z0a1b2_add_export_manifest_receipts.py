"""Add export manifest receipt fields.

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-07-04 15:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "w7x8y9z0a1b2"
down_revision: str | Sequence[str] | None = "v6w7x8y9z0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "export_jobs",
        sa.Column("manifest_schema_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "export_jobs",
        sa.Column("manifest_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "export_jobs",
        sa.Column(
            "manifest_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "export_jobs",
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "export_jobs",
        sa.Column("report_payload_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "export_jobs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_export_jobs_org_manifest_hash", "export_jobs", ["org_id", "manifest_hash"])


def downgrade() -> None:
    op.drop_index("ix_export_jobs_org_manifest_hash", table_name="export_jobs")
    op.drop_column("export_jobs", "completed_at")
    op.drop_column("export_jobs", "report_payload_sha256")
    op.drop_column("export_jobs", "artifact_sha256")
    op.drop_column("export_jobs", "manifest_snapshot")
    op.drop_column("export_jobs", "manifest_hash")
    op.drop_column("export_jobs", "manifest_schema_version")

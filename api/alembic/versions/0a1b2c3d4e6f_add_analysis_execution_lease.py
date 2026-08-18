"""Add idempotent pipeline execution lease fields.

Revision ID: 0a1b2c3d4e6f
Revises: f6a7b8c9d0e1
Create Date: 2026-05-25 00:00:00.000000

Cloud Tasks may deliver the same pipeline request more than once. These
nullable fields let workers acquire an analysis-level lease atomically, skip
active duplicates, and retry stale failed executions without rerunning
completed/cancelled/deleted analyses.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0a1b2c3d4e6f"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("pipeline_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column("pipeline_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_analyses_pipeline_lease",
        "analyses",
        ["status", "pipeline_lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_pipeline_lease", table_name="analyses")
    op.drop_column("analyses", "pipeline_lease_expires_at")
    op.drop_column("analyses", "pipeline_execution_id")

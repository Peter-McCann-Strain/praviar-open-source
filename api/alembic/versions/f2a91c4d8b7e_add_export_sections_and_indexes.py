"""Add export sections column and performance indexes.

Revision ID: f2a91c4d8b7e
Revises: e1b31753ec2c
Create Date: 2026-03-23 12:00:00.000000

This migration demonstrates the incremental migration pattern for the project.
It adds a sections column to export_jobs (to track which report sections were
requested) and adds performance indexes identified during load testing.

To apply:
    cd api && alembic upgrade head

To rollback:
    cd api && alembic downgrade e1b31753ec2c
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a91c4d8b7e"
down_revision: str | None = "e1b31753ec2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add sections column to export_jobs — tracks which report sections were included
    op.add_column(
        "export_jobs",
        sa.Column(
            "sections",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )

    # Add error_message column to export_jobs for debugging failed exports
    op.add_column(
        "export_jobs",
        sa.Column("error_message", sa.Text(), server_default="", nullable=False),
    )

    # Performance indexes identified during load testing
    # Speed up export status polling (frontend polls every 2s)
    op.create_index(
        "ix_export_jobs_user_status",
        "export_jobs",
        ["user_id", "status"],
    )

    # Speed up comment listing by analysis (used on report page Comments tab)
    op.create_index(
        "ix_comments_target",
        "comments",
        ["target_type", "target_id"],
    )

    # Speed up feedback lookup by analysis
    op.create_index(
        "ix_attorney_feedback_analysis",
        "attorney_feedback",
        ["analysis_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_attorney_feedback_analysis", table_name="attorney_feedback")
    op.drop_index("ix_comments_target", table_name="comments")
    op.drop_index("ix_export_jobs_user_status", table_name="export_jobs")
    op.drop_column("export_jobs", "error_message")
    op.drop_column("export_jobs", "sections")

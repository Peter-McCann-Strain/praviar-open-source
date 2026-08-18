"""Add analysis_reviewer_decisions table for attorney accept/reject/edit workflow.

Revision ID: d7e5a2c1b8f9
Revises: f2a91c4d8b7e
Create Date: 2026-04-15 10:00:00.000000

Adds the ``analysis_reviewer_decisions`` table that records per-finding
accept / reject / edit decisions captured in the UI, authored by an identified
reviewer (via Clerk). One row per (analysis, finding, reviewer).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e5a2c1b8f9"
down_revision: str | None = "f2a91c4d8b7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_reviewer_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("finding_type", sa.String(length=32), nullable=False),
        sa.Column("finding_ref", sa.String(length=512), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("edited_text", sa.Text(), server_default="", nullable=False),
        sa.Column("reviewer_user_id", sa.String(length=255), nullable=False),
        sa.Column("reviewer_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("reviewer_email", sa.String(length=255), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_analysis_reviewer_decisions_analysis_id",
        "analysis_reviewer_decisions",
        ["analysis_id"],
    )
    op.create_index(
        "ix_analysis_reviewer_decisions_org_id",
        "analysis_reviewer_decisions",
        ["org_id"],
    )
    op.create_index(
        "ix_decisions_analysis_org",
        "analysis_reviewer_decisions",
        ["analysis_id", "org_id"],
    )
    op.create_index(
        "ix_decisions_unique_reviewer_finding",
        "analysis_reviewer_decisions",
        ["analysis_id", "finding_type", "finding_ref", "reviewer_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_decisions_unique_reviewer_finding",
        table_name="analysis_reviewer_decisions",
    )
    op.drop_index("ix_decisions_analysis_org", table_name="analysis_reviewer_decisions")
    op.drop_index(
        "ix_analysis_reviewer_decisions_org_id",
        table_name="analysis_reviewer_decisions",
    )
    op.drop_index(
        "ix_analysis_reviewer_decisions_analysis_id",
        table_name="analysis_reviewer_decisions",
    )
    op.drop_table("analysis_reviewer_decisions")

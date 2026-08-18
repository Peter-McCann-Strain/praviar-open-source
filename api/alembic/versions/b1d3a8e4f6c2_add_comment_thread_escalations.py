"""Add persisted thread-level comment escalation state.

Revision ID: b1d3a8e4f6c2
Revises: 9c2f4a7d1c6b
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "b1d3a8e4f6c2"
down_revision: str | Sequence[str] | None = "9c2f4a7d1c6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment_thread_escalations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "comment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("comments.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "escalated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "escalated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "escalation_status", sa.String(length=32), nullable=False, server_default="escalated"
        ),
        sa.Column(
            "escalated_to_review", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "review_handoff_comment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("comments.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_comment_thread_escalations_comment_org",
        "comment_thread_escalations",
        ["comment_id", "org_id"],
        unique=True,
    )
    op.create_index(
        "ix_comment_thread_escalations_analysis_org",
        "comment_thread_escalations",
        ["analysis_id", "org_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_comment_thread_escalations_analysis_org",
        table_name="comment_thread_escalations",
    )
    op.drop_index(
        "ix_comment_thread_escalations_comment_org",
        table_name="comment_thread_escalations",
    )
    op.drop_table("comment_thread_escalations")

"""Add append-only comment assignment events.

Revision ID: 9c2f4a7d1c6b
Revises: 7b1c9d4f2e18
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "9c2f4a7d1c6b"
down_revision: str | Sequence[str] | None = "7b1c9d4f2e18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment_assignment_events",
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
            "assigned_to",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "assigned_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_comment_assignment_events_comment_created",
        "comment_assignment_events",
        ["comment_id", "created_at"],
    )
    op.create_index(
        "ix_comment_assignment_events_analysis_org_created",
        "comment_assignment_events",
        ["analysis_id", "org_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_comment_assignment_events_analysis_org_created",
        table_name="comment_assignment_events",
    )
    op.drop_index(
        "ix_comment_assignment_events_comment_created",
        table_name="comment_assignment_events",
    )
    op.drop_table("comment_assignment_events")

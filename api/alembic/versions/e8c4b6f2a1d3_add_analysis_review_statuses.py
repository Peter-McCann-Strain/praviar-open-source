"""Add persisted report-level review workflow state.

Revision ID: e8c4b6f2a1d3
Revises: b4d81e2f3a9c, c9b3414ef321, d7e5a2c1b8f9
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e8c4b6f2a1d3"
down_revision: str | Sequence[str] | None = (
    "b4d81e2f3a9c",
    "c9b3414ef321",
    "d7e5a2c1b8f9",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Explicitly create the enum here, then reference it on the column with
    # ``create_type=False`` so SQLAlchemy does not attempt to auto-create the
    # type a second time during ``op.create_table`` (which would raise
    # ``DuplicateObject`` on a fresh Postgres DB). Mirrors the canonical
    # pattern from a3c72f9e1d4b_add_billing_notifications_models.py.
    reviewstatus_enum = postgresql.ENUM(
        "pending",
        "under_review",
        "approved",
        "changes_requested",
        name="reviewstatus",
    )
    reviewstatus_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "analysis_review_statuses",
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
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "under_review",
                "approved",
                "changes_requested",
                name="reviewstatus",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("reviewer_user_id", sa.String(length=255), nullable=False),
        sa.Column("reviewer_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("reviewer_email", sa.String(length=255), server_default="", nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_analysis_review_statuses_org",
        "analysis_review_statuses",
        ["org_id"],
    )
    op.create_index(
        "ix_analysis_review_statuses_analysis_org",
        "analysis_review_statuses",
        ["analysis_id", "org_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_review_statuses_analysis_org",
        table_name="analysis_review_statuses",
    )
    op.drop_index("ix_analysis_review_statuses_org", table_name="analysis_review_statuses")
    op.drop_table("analysis_review_statuses")
    postgresql.ENUM(name="reviewstatus").drop(op.get_bind(), checkfirst=True)

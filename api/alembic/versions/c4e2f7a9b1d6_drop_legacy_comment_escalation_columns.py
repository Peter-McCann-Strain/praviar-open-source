"""Drop legacy comment-level escalation columns.

Revision ID: c4e2f7a9b1d6
Revises: b1d3a8e4f6c2
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "c4e2f7a9b1d6"
down_revision: str | Sequence[str] | None = "b1d3a8e4f6c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("comments", "escalated_at")
    op.drop_column("comments", "escalated_by")


def downgrade() -> None:
    op.add_column(
        "comments",
        sa.Column("escalated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "comments",
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
    )

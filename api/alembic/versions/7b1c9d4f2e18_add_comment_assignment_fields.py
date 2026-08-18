"""Add assignment metadata to comments.

Revision ID: 7b1c9d4f2e18
Revises: 3f9f2e1c7c4a
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "7b1c9d4f2e18"
down_revision: str | Sequence[str] | None = "3f9f2e1c7c4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comments",
        sa.Column("assigned_to", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "comments",
        sa.Column("assigned_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "comments",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("comments", "assigned_at")
    op.drop_column("comments", "assigned_by")
    op.drop_column("comments", "assigned_to")

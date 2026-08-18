"""Add resolved_at timestamp to comments.

Revision ID: 3f9f2e1c7c4a
Revises: e8c4b6f2a1d3
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3f9f2e1c7c4a"
down_revision: str | Sequence[str] | None = "e8c4b6f2a1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comments",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("comments", "resolved_at")

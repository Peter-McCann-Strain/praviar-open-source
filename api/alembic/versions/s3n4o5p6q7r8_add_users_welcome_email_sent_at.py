"""Add welcome_email_sent_at to users for idempotent welcome email dispatch.

Revision ID: s3n4o5p6q7r8
Revises: r2m3n4o5p6q7
Create Date: 2026-06-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "s3n4o5p6q7r8"
down_revision: str | Sequence[str] | None = "r2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("welcome_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "welcome_email_sent_at")

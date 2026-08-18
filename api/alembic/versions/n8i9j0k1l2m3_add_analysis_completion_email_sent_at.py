"""Add completion_email_sent_at to analyses for idempotent email dispatch.

Revision ID: n8i9j0k1l2m3
Revises: m7h8i9j0k1l2
Create Date: 2026-06-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "n8i9j0k1l2m3"
down_revision: str | Sequence[str] | None = "m7h8i9j0k1l2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("completion_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analyses", "completion_email_sent_at")

"""Add email_sent_at to monitor_alerts for idempotent email dispatch.

Revision ID: m7h8i9j0k1l2
Revises: l6g7h8i9j0k1
Create Date: 2026-06-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m7h8i9j0k1l2"
down_revision: str | Sequence[str] | None = "l6g7h8i9j0k1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitor_alerts",
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitor_alerts", "email_sent_at")

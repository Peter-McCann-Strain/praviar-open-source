"""Add report fingerprint to reviewer decisions.

Revision ID: 8a6b4d2c9e1f
Revises: 7e8f9a0b1c2d
Create Date: 2026-06-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8a6b4d2c9e1f"
down_revision: str | Sequence[str] | None = "7e8f9a0b1c2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_reviewer_decisions",
        sa.Column("report_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_reviewer_decisions", "report_fingerprint")

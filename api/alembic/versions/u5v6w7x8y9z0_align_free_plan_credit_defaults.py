"""Align free plan report-credit defaults.

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-07-02 16:25:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "u5v6w7x8y9z0"
down_revision: str | Sequence[str] | None = "t4u5v6w7x8y9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "organizations",
        "max_analyses_per_month",
        existing_type=sa.Integer(),
        server_default="2",
        existing_nullable=False,
    )
    op.execute(
        """
        UPDATE organizations
        SET
            max_analyses_per_month = 2,
            free_analyses_remaining = LEAST(free_analyses_remaining, 2)
        WHERE plan = 'free'
          AND max_analyses_per_month = 10
        """
    )


def downgrade() -> None:
    op.alter_column(
        "organizations",
        "max_analyses_per_month",
        existing_type=sa.Integer(),
        server_default="10",
        existing_nullable=False,
    )

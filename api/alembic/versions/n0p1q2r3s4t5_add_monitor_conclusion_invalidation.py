"""Persist conclusion-aware monitor invalidation state.

Revision ID: n0p1q2r3s4t5
Revises: c3d4e5f6a7b8
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "n0p1q2r3s4t5"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column(
            "conclusion_status",
            sa.String(length=32),
            server_default="unbound",
            nullable=False,
        ),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "stale_conclusions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE monitors
           SET conclusion_status = 'fresh'
         WHERE source_analysis_id IS NOT NULL
        """
    )
    op.create_check_constraint(
        "ck_monitors_conclusion_status",
        "monitors",
        "conclusion_status IN ('unbound', 'fresh', 'review_required')",
    )
    op.add_column(
        "monitor_alerts",
        sa.Column(
            "affected_conclusions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("monitor_alerts", "affected_conclusions")
    op.drop_constraint(
        "ck_monitors_conclusion_status",
        "monitors",
        type_="check",
    )
    op.drop_column("monitors", "stale_conclusions")
    op.drop_column("monitors", "conclusion_status")

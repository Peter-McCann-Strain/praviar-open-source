"""Persist the exact transition time for completed analyses.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-07-16 23:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Historical rows lack an exact transition event. Backfill conservatively
    # from creation plus recorded pipeline duration so deployment cannot make
    # old reports appear newly completed merely because they were edited later.
    op.execute(
        """
        UPDATE analyses
        SET completed_at = created_at
            + (
                GREATEST(COALESCE(pipeline_duration_seconds, 0), 0)
                * INTERVAL '1 second'
            )
        WHERE status = 'completed'
          AND completed_at IS NULL
        """
    )
    op.create_check_constraint(
        "ck_analyses_completed_at_present",
        "analyses",
        "status <> 'completed' OR completed_at IS NOT NULL",
    )
    op.create_index(
        "ix_analyses_org_status_completed_at",
        "analyses",
        ["org_id", "status", "completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_org_status_completed_at", table_name="analyses")
    op.drop_constraint(
        "ck_analyses_completed_at_present",
        "analyses",
        type_="check",
    )
    op.drop_column("analyses", "completed_at")

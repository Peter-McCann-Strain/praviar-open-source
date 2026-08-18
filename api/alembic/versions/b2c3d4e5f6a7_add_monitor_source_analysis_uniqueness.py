"""Prevent duplicate report-seeded monitors.

Revision ID: b2c3d4e5f6a7
Revises: a2b3c4d5e6f7
Create Date: 2026-07-17 17:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the first monitor created for a report. Preserve the history carried
    # by later accidental duplicates by re-parenting their alerts before the
    # duplicate monitor rows are removed.
    op.execute(
        sa.text(
            """
            WITH ranked_monitors AS (
                SELECT
                    id,
                    first_value(id) OVER (
                        PARTITION BY org_id, source_analysis_id
                        ORDER BY created_at ASC, id ASC
                    ) AS canonical_id,
                    row_number() OVER (
                        PARTITION BY org_id, source_analysis_id
                        ORDER BY created_at ASC, id ASC
                    ) AS duplicate_rank
                FROM monitors
                WHERE source_analysis_id IS NOT NULL
            )
            UPDATE monitor_alerts AS alerts
            SET monitor_id = ranked.canonical_id
            FROM ranked_monitors AS ranked
            WHERE ranked.duplicate_rank > 1
              AND alerts.monitor_id = ranked.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ranked_monitors AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY org_id, source_analysis_id
                        ORDER BY created_at ASC, id ASC
                    ) AS duplicate_rank
                FROM monitors
                WHERE source_analysis_id IS NOT NULL
            )
            DELETE FROM monitors AS duplicate
            USING ranked_monitors AS ranked
            WHERE ranked.duplicate_rank > 1
              AND duplicate.id = ranked.id
            """
        )
    )
    op.create_index(
        "uq_monitors_org_source_analysis_id",
        "monitors",
        ["org_id", "source_analysis_id"],
        unique=True,
        postgresql_where=sa.text("source_analysis_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_monitors_org_source_analysis_id",
        table_name="monitors",
    )

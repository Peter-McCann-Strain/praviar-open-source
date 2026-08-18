"""Add persisted monitor strategy, snapshot, and alert metadata.

Revision ID: f4c8a2d6b9e1
Revises: e8c4b6f2a1d3
Create Date: 2026-04-24 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f4c8a2d6b9e1"
down_revision: str | Sequence[str] | None = "e8c4b6f2a1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column(
            "source_analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "monitors",
        sa.Column("source_report_id", sa.String(length=100), server_default="", nullable=False),
    )
    op.add_column(
        "monitors",
        sa.Column("source_trust_mode", sa.String(length=20), server_default="", nullable=False),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "jurisdiction_bundle", sa.String(length=50), server_default="custom", nullable=False
        ),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "target_jurisdictions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "strategy_version",
            sa.String(length=50),
            server_default="2026-04-monitor-v1",
            nullable=False,
        ),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "monitoring_strategy",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "watch_targets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitors", sa.Column("last_full_refresh_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "monitors",
        sa.Column("last_run_mode", sa.String(length=30), server_default="", nullable=False),
    )
    op.add_column(
        "monitors",
        sa.Column("last_run_status", sa.String(length=30), server_default="", nullable=False),
    )
    op.add_column(
        "monitors", sa.Column("last_run_summary", sa.Text(), server_default="", nullable=False)
    )
    op.add_column(
        "monitors",
        sa.Column(
            "last_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.add_column(
        "monitor_alerts",
        sa.Column(
            "alert_type", sa.String(length=50), server_default="new_patent_delta", nullable=False
        ),
    )
    op.add_column(
        "monitor_alerts",
        sa.Column("severity", sa.String(length=20), server_default="medium", nullable=False),
    )
    op.add_column(
        "monitor_alerts", sa.Column("summary", sa.Text(), server_default="", nullable=False)
    )
    op.add_column(
        "monitor_alerts",
        sa.Column("strategy_mode", sa.String(length=30), server_default="", nullable=False),
    )
    op.add_column(
        "monitor_alerts",
        sa.Column(
            "new_event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitor_alerts",
        sa.Column(
            "jurisdiction_deltas",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("monitor_alerts", "jurisdiction_deltas")
    op.drop_column("monitor_alerts", "new_event_ids")
    op.drop_column("monitor_alerts", "strategy_mode")
    op.drop_column("monitor_alerts", "summary")
    op.drop_column("monitor_alerts", "severity")
    op.drop_column("monitor_alerts", "alert_type")

    op.drop_column("monitors", "last_snapshot")
    op.drop_column("monitors", "last_run_summary")
    op.drop_column("monitors", "last_run_status")
    op.drop_column("monitors", "last_run_mode")
    op.drop_column("monitors", "last_full_refresh_at")
    op.drop_column("monitors", "watch_targets")
    op.drop_column("monitors", "monitoring_strategy")
    op.drop_column("monitors", "strategy_version")
    op.drop_column("monitors", "target_jurisdictions")
    op.drop_column("monitors", "jurisdiction_bundle")
    op.drop_column("monitors", "source_trust_mode")
    op.drop_column("monitors", "source_report_id")
    op.drop_column("monitors", "source_analysis_id")

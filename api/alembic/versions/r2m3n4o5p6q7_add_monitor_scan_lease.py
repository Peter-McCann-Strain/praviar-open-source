"""Add scan_execution_id and scan_lease_expires_at to monitors.

Implements a durable execution lease for monitor scans, mirroring the
pipeline/export lease pattern. The worker sets these fields at scan start so
that a crashed run leaves a visible marker; load_due_monitor_refs skips monitors
whose lease is still live and reclaims them once the lease expires.

Revision ID: r2m3n4o5p6q7
Revises: q1l2m3n4o5p6
Create Date: 2026-06-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "r2m3n4o5p6q7"
down_revision: str | Sequence[str] | None = "q1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column("scan_execution_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "scan_lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_monitors_scan_lease",
        "monitors",
        ["scan_lease_expires_at"],
        postgresql_where=sa.text("scan_lease_expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_monitors_scan_lease", table_name="monitors")
    op.drop_column("monitors", "scan_lease_expires_at")
    op.drop_column("monitors", "scan_execution_id")

"""Add Stripe webhook processing lease.

Revision ID: 5d0e7a9c2b1f
Revises: 2b7d6f9a4c1e
Create Date: 2026-06-02 00:00:00.000000

Stripe can redeliver the same event while the first delivery is still being
handled. The nullable lease blocks concurrent duplicate execution while letting
expired or failed receipts be reclaimed by later Stripe retries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "5d0e7a9c2b1f"
down_revision: str | Sequence[str] | None = "2b7d6f9a4c1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stripe_events",
        sa.Column("processing_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "stripe_events",
        sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_stripe_events_processing_lease",
        "stripe_events",
        ["processed", "processing_lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stripe_events_processing_lease", table_name="stripe_events")
    op.drop_column("stripe_events", "processing_lease_expires_at")
    op.drop_column("stripe_events", "processing_execution_id")

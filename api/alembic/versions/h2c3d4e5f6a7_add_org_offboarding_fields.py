"""Add org offboarding/deletion fields.

Adds deletion_scheduled_at, deletion_requested_by, and deletion_status to
organizations so the platform can honour GDPR/UK data erasure requests and
track the lifecycle of tenant offboarding.

Revision ID: h2c3d4e5f6a7
Revises: g1b2c3d4e5f6
Create Date: 2026-06-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "h2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "g1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "deletion_scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=None,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "deletion_requested_by",
            sa.String(255),
            nullable=True,
            server_default=None,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "deletion_status",
            sa.String(50),
            nullable=True,
            server_default=None,
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "deletion_status")
    op.drop_column("organizations", "deletion_requested_by")
    op.drop_column("organizations", "deletion_scheduled_at")

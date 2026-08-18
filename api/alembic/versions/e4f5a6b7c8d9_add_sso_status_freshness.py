"""Add durable SSO status freshness, refresh ordering, and policy.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-14 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | Sequence[str] | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "sso_required",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE organizations SET sso_required = true "
            "WHERE settings ->> 'sso_required' = 'true'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE organizations SET settings = settings - 'sso_required' "
            "WHERE settings ? 'sso_required'"
        )
    )
    op.add_column(
        "organizations",
        sa.Column(
            "sso_status_available",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("sso_last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "sso_last_refresh_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "sso_refresh_attempt_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE organizations SET settings = jsonb_set("
            "COALESCE(settings, '{}'::jsonb), '{sso_required}', "
            "to_jsonb(sso_required), true)"
        )
    )
    op.drop_column("organizations", "sso_refresh_attempt_id")
    op.drop_column("organizations", "sso_last_refresh_started_at")
    op.drop_column("organizations", "sso_last_synced_at")
    op.drop_column("organizations", "sso_status_available")
    op.drop_column("organizations", "sso_required")

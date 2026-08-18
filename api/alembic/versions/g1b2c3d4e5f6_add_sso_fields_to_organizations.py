"""Add SSO fields to organizations table.

Revision ID: g1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-06-08 00:00:00.000000

Adds three columns to the organizations table to track Clerk Enterprise
Connection (SAML/OIDC) state so the application can surface SSO status
to org admins without querying the Clerk Backend API on every request.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "g1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "9d4e2f6a1b3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("sso_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "organizations",
        sa.Column("sso_provider", sa.String(100), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("sso_domains", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("organizations", "sso_domains")
    op.drop_column("organizations", "sso_provider")
    op.drop_column("organizations", "sso_enabled")

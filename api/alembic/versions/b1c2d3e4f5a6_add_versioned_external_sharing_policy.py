"""Add fail-closed versioned external sharing policy columns.

Revision ID: b1c2d3e4f5a6
Revises: z0a1b2c3d4e5
Create Date: 2026-07-14 02:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "z0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deliberate authorization reset: every existing tenant starts deny-all.
    # We do not coerce even well-formed legacy JSON because it was unversioned,
    # had no optimistic-concurrency contract, and cannot prove an administrator
    # reviewed its current impact. Malformed and well-formed legacy values are
    # both removed; an admin must explicitly enable sharing through the new
    # versioned API and its server-authoritative impact confirmation.
    op.add_column(
        "organizations",
        sa.Column(
            "external_sharing_policy_mode",
            sa.String(32),
            server_default="approved_domains_only",
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "external_sharing_approved_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "external_sharing_policy_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_organizations_external_sharing_policy_mode",
        "organizations",
        "external_sharing_policy_mode IN ('open', 'approved_domains_only')",
    )
    op.create_check_constraint(
        "ck_organizations_external_sharing_policy_version_positive",
        "organizations",
        "external_sharing_policy_version > 0",
    )
    op.execute(
        "UPDATE organizations SET settings = settings - 'external_sharing_policy' "
        "WHERE settings ? 'external_sharing_policy'"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_organizations_external_sharing_policy_version_positive",
        "organizations",
        type_="check",
    )
    op.drop_constraint(
        "ck_organizations_external_sharing_policy_mode",
        "organizations",
        type_="check",
    )
    op.drop_column("organizations", "external_sharing_policy_version")
    op.drop_column("organizations", "external_sharing_approved_domains")
    op.drop_column("organizations", "external_sharing_policy_mode")

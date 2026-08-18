"""Enforce inactive state for deleted Clerk memberships.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-07-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET membership_active = false "
        "WHERE membership_deleted_at IS NOT NULL AND membership_active = true"
    )
    op.create_check_constraint(
        "ck_users_deleted_membership_inactive",
        "users",
        "membership_deleted_at IS NULL OR NOT membership_active",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_deleted_membership_inactive",
        "users",
        type_="check",
    )

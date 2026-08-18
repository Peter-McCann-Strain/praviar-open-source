"""Add composite index on users(org_id, role) for review queue queries.

Revision ID: p0k1l2m3n4o5
Revises: o9j0k1l2m3n4
Create Date: 2026-06-16

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "p0k1l2m3n4o5"
down_revision: str | Sequence[str] | None = "o9j0k1l2m3n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_users_org_role", "users", ["org_id", "role"])


def downgrade() -> None:
    op.drop_index("ix_users_org_role", table_name="users")

"""Add audience column to export_jobs.

Revision ID: j4e5f6a7b8c9
Revises: i3d4e5f6a7b8
Create Date: 2026-06-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "i3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "export_jobs",
        sa.Column(
            "audience",
            sa.String(32),
            server_default="full",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("export_jobs", "audience")

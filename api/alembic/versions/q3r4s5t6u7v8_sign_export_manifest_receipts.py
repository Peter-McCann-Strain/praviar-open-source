"""Sign export manifest receipts.

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-07-26 18:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "q3r4s5t6u7v8"
down_revision: str | Sequence[str] | None = "p2q3r4s5t6u7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "export_jobs",
        sa.Column("manifest_signature", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("export_jobs", "manifest_signature")

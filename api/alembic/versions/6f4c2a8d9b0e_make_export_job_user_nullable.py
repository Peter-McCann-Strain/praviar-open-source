"""Make export job requester nullable for SET NULL user deletion.

Revision ID: 6f4c2a8d9b0e
Revises: 5d0e7a9c2b1f
Create Date: 2026-06-03 00:00:00.000000

The ORM and 0043 FK policy intentionally allow export jobs to outlive user
deletion by setting ``export_jobs.user_id`` to NULL. Older databases can still
carry the initial NOT NULL constraint, so align the physical schema with that
runtime contract.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "6f4c2a8d9b0e"
down_revision: str | Sequence[str] | None = "5d0e7a9c2b1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXPORT_JOBS_TABLE = "export_jobs"
EXPORT_JOB_USER_ID_COLUMN = "user_id"


def upgrade() -> None:
    op.alter_column(
        EXPORT_JOBS_TABLE,
        EXPORT_JOB_USER_ID_COLUMN,
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        EXPORT_JOBS_TABLE,
        EXPORT_JOB_USER_ID_COLUMN,
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

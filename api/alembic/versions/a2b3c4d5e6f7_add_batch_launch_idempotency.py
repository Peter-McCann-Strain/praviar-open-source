"""Add durable batch-launch idempotency receipts.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-17 15:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batch_analyses",
        sa.Column("launch_idempotency_key_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "batch_analyses",
        sa.Column("launch_payload_digest", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_batch_analyses_launch_idempotency_pair",
        "batch_analyses",
        "(launch_idempotency_key_digest IS NULL "
        "AND launch_payload_digest IS NULL) OR "
        "(launch_idempotency_key_digest IS NOT NULL "
        "AND launch_payload_digest IS NOT NULL "
        "AND launch_idempotency_key_digest ~ '^[0-9a-f]{64}$' "
        "AND launch_payload_digest ~ '^[0-9a-f]{64}$')",
    )
    op.create_index(
        "uq_batch_analyses_org_launch_idempotency",
        "batch_analyses",
        ["org_id", "launch_idempotency_key_digest"],
        unique=True,
        postgresql_where=sa.text("launch_idempotency_key_digest IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_batch_analyses_org_launch_idempotency",
        table_name="batch_analyses",
    )
    op.drop_constraint(
        "ck_batch_analyses_launch_idempotency_pair",
        "batch_analyses",
        type_="check",
    )
    op.drop_column("batch_analyses", "launch_payload_digest")
    op.drop_column("batch_analyses", "launch_idempotency_key_digest")

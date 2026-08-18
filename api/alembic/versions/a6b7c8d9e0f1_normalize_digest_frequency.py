"""Normalize unsupported digest cadences to the scheduled weekly cadence.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-07-16 22:25:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | Sequence[str] | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET preferences = jsonb_set(
            COALESCE(preferences, '{}'::jsonb),
            '{email_digest_frequency}',
            '"weekly"'::jsonb,
            true
        )
        WHERE preferences ->> 'email_digest_frequency'
            IN ('daily', 'immediate')
        """
    )


def downgrade() -> None:
    # The prior value cannot be reconstructed after normalization. Keeping
    # "weekly" is safer than reintroducing a cadence the runtime cannot send.
    pass

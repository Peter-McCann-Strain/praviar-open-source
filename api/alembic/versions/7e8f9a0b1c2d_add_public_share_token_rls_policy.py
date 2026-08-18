"""Add token-bound RLS policy for public share lookup.

Revision ID: 7e8f9a0b1c2d
Revises: 6f4c2a8d9b0e
Create Date: 2026-06-03 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "7e8f9a0b1c2d"
down_revision: str | Sequence[str] | None = "6f4c2a8d9b0e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        """
        DROP POLICY IF EXISTS public_share_token_lookup ON analyses;
        """
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        """
        CREATE POLICY public_share_token_lookup ON analyses
            FOR SELECT
            USING (
                share_token IS NOT NULL
                AND share_token = current_setting('app.public_share_token', true)
            );
        """
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        """
        COMMENT ON POLICY public_share_token_lookup ON analyses IS
            'Unauthenticated public share lookup is limited to the exact token '
            'bound in app.public_share_token for the current transaction.';
        """
    )


def downgrade() -> None:
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        "DROP POLICY IF EXISTS public_share_token_lookup ON analyses;"
    )

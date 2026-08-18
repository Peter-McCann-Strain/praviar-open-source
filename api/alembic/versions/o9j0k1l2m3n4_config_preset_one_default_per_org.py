"""Add partial unique index: at most one default config preset per org.

Revision ID: o9j0k1l2m3n4
Revises: n8i9j0k1l2m3
Create Date: 2026-06-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "o9j0k1l2m3n4"
down_revision: str | Sequence[str] | None = "n8i9j0k1l2m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Before this index existed, create_preset cleared existing defaults and
    # inserted the new default in two non-atomic steps, so two concurrent
    # is_default=True creates could both commit, leaving an org with more than
    # one default preset. A UNIQUE index validates against current data, so on
    # any such table this migration would abort the deploy. Demote all but the
    # most recently created default per org first (newest created_at, tie-broken
    # by id). The UPDATE is a no-op on a table that already has at most one
    # default per org.
    op.execute(
        sa.text(
            """
            UPDATE config_presets AS cp
            SET is_default = FALSE
            WHERE cp.is_default = TRUE
              AND EXISTS (
                  SELECT 1
                  FROM config_presets AS keep
                  WHERE keep.org_id = cp.org_id
                    AND keep.is_default = TRUE
                    AND (keep.created_at, keep.id) > (cp.created_at, cp.id)
              )
            """
        )
    )
    # Build the partial unique index CONCURRENTLY so it does not take an ACCESS
    # EXCLUSIVE lock on config_presets for the duration of the build (a plain
    # CREATE INDEX would block all writes to the table). env.py wraps every
    # migration in a transaction; CREATE INDEX CONCURRENTLY cannot run inside
    # one, so escape via autocommit_block. if_not_exists makes this safe to
    # re-run after a CONCURRENTLY build that failed partway (leaving an INVALID
    # index behind).
    with op.get_context().autocommit_block():
        op.create_index(
            "uq_config_presets_org_one_default",
            "config_presets",
            ["org_id"],
            unique=True,
            postgresql_where="is_default = TRUE",
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "uq_config_presets_org_one_default",
            table_name="config_presets",
            postgresql_concurrently=True,
            if_exists=True,
        )

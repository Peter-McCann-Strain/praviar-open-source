"""Add missing FK indexes on analyses.initiated_by and audit_logs.user_id.

Revision ID: l6g7h8i9j0k1
Revises: k5f6a7b8c9d0
Create Date: 2026-06-14 00:00:00.000000

Migration 0043 added SET NULL FK constraints on analyses.initiated_by and
audit_logs.user_id (via the users table) but did not create indexes on those
columns. Without indexes, a user-deletion cascade must full-scan both tables to
find rows to NULL-out. These are additive, lock-free (CONCURRENTLY) indexes.

INFRA-006: analyses.initiated_by
INFRA-008: audit_logs.user_id
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "l6g7h8i9j0k1"
down_revision: str | Sequence[str] | None = "k5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block. env.py
    # wraps every migration in begin_transaction(), so escape it via
    # autocommit_block() before issuing the concurrent builds. Without this,
    # these become plain CREATE INDEX statements that take an ACCESS EXCLUSIVE
    # lock and block all writes to analyses and audit_logs for the duration of
    # the build — a write-blocking outage on the two highest-write tables.
    # if_not_exists makes the migration safe to re-run after a CONCURRENTLY
    # build that failed partway (which leaves an INVALID index behind).
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_analyses_initiated_by",
            "analyses",
            ["initiated_by"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "ix_audit_logs_user_id",
            "audit_logs",
            ["user_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_audit_logs_user_id",
            table_name="audit_logs",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_analyses_initiated_by",
            table_name="analyses",
            postgresql_concurrently=True,
            if_exists=True,
        )

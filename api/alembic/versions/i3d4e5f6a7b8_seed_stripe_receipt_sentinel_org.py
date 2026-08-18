"""Seed the Stripe receipt sentinel organization row.

Stripe webhooks for unresolved orgs (e.g. checkout.session.completed arriving
before the org metadata is written) are stored with org_id = nil UUID
(00000000-0000-0000-0000-000000000000) to satisfy the RLS WITH CHECK constraint.
stripe_events.org_id has a FK to organizations.id, so inserting the nil UUID
requires a matching organizations row to exist.

This migration seeds that sentinel row.  It is intentionally never deleted;
org_id is backfilled to the real org once the org is resolved.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "i3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "h2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        INSERT INTO organizations (
            id, clerk_org_id, name, slug, plan,
            max_analyses_per_month, free_analyses_remaining,
            settings, sso_enabled, sso_domains,
            cancel_at_period_end, analyses_used_this_month
        ) VALUES (
            '{NIL_UUID}',
            '__stripe_receipt_sentinel__',
            'Stripe Receipt Sentinel',
            '__sentinel__',
            'free',
            0, 0,
            '{{}}', false, '[]',
            false, 0
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"DELETE FROM organizations WHERE id = '{NIL_UUID}';"
    )

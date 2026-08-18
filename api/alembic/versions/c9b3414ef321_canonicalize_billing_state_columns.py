"""Canonicalize billing state onto typed organization columns.

Revision ID: c9b3414ef321
Revises: a3c72f9e1d4b
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9b3414ef321"
down_revision: str | None = "a3c72f9e1d4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("subscription_status", sa.String(50), nullable=True))
    op.add_column(
        "organizations", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "organizations",
        sa.Column(
            "cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    op.execute(
        """
        UPDATE organizations
        SET stripe_customer_id = COALESCE(stripe_customer_id, settings->>'stripe_customer_id'),
            stripe_subscription_id = COALESCE(stripe_subscription_id, settings->>'stripe_subscription_id'),
            subscription_status = COALESCE(subscription_status, settings->>'subscription_status'),
            billing_cycle_start = COALESCE(
                billing_cycle_start,
                to_timestamp(NULLIF(settings->>'current_period_start', '')::double precision)
            ),
            current_period_end = COALESCE(
                current_period_end,
                to_timestamp(NULLIF(settings->>'current_period_end', '')::double precision)
            ),
            cancel_at_period_end = COALESCE(
                NULLIF(settings->>'cancel_at_period_end', '')::boolean,
                cancel_at_period_end
            )
        WHERE settings IS NOT NULL
        """
    )


def downgrade() -> None:
    # Write billing state back into settings JSONB before dropping the typed columns
    # so that a subsequent re-upgrade can recover the data.
    op.execute(
        """
        UPDATE organizations
        SET settings = COALESCE(settings, '{}'::jsonb)
            || jsonb_strip_nulls(jsonb_build_object(
                'stripe_customer_id',     stripe_customer_id,
                'stripe_subscription_id', stripe_subscription_id,
                'subscription_status',    subscription_status,
                'current_period_end',     EXTRACT(EPOCH FROM current_period_end),
                'cancel_at_period_end',   cancel_at_period_end::text
            ))
        WHERE subscription_status IS NOT NULL
           OR current_period_end IS NOT NULL
           OR cancel_at_period_end = true
        """
    )
    op.drop_column("organizations", "cancel_at_period_end")
    op.drop_column("organizations", "current_period_end")
    op.drop_column("organizations", "subscription_status")

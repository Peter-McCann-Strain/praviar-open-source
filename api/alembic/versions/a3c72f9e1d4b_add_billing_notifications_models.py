"""Add billing fields, notifications, and Stripe event tracking.

Revision ID: a3c72f9e1d4b
Revises: f2a91c4d8b7e
Create Date: 2026-03-29 00:00:00.000000

Adds:
- STARTER to org_plan enum
- Stripe billing fields on organizations
- Notification model and type enum
- StripeEvent idempotency model
- Share analytics fields on analyses

To apply:
    cd api && alembic upgrade head

To rollback:
    cd api && alembic downgrade f2a91c4d8b7e
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c72f9e1d4b"
down_revision: str | None = "f2a91c4d8b7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Add STARTER to org_plan enum ---
    op.execute("ALTER TYPE orgplan ADD VALUE IF NOT EXISTS 'starter' BEFORE 'pro'")

    # --- Add Stripe fields to organizations ---
    op.add_column(
        "organizations", sa.Column("stripe_customer_id", sa.String(255), unique=True, nullable=True)
    )
    op.add_column(
        "organizations", sa.Column("stripe_subscription_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "organizations", sa.Column("billing_cycle_start", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "organizations",
        sa.Column("analyses_used_this_month", sa.Integer(), server_default="0", nullable=False),
    )

    # --- Add share analytics to analyses ---
    op.add_column(
        "analyses", sa.Column("share_view_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "analyses", sa.Column("share_last_viewed_at", sa.DateTime(timezone=True), nullable=True)
    )

    # --- Create notification_type enum ---
    # Explicitly create the enum here, then reference it on the column with
    # ``create_type=False`` so SQLAlchemy does not attempt to auto-create the
    # type a second time during ``op.create_table`` (which would raise
    # ``DuplicateObject`` on a fresh Postgres DB). This mirrors the pattern in
    # b4d81e2f3a9c_add_monitors_apikeys_batch_tables.py.
    notification_type = postgresql.ENUM(
        "analysis_complete",
        "monitor_alert",
        "export_ready",
        "team_invite",
        "billing_event",
        "system",
        name="notificationtype",
    )
    notification_type.create(op.get_bind(), checkfirst=True)

    # --- Create notifications table ---
    op.create_table(
        "notifications",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "analysis_complete",
                "monitor_alert",
                "export_ready",
                "team_invite",
                "billing_event",
                "system",
                name="notificationtype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("data", JSONB, server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_notifications_user_read", "notifications", ["user_id", "read", "created_at"]
    )

    # --- Create stripe_events table ---
    op.create_table(
        "stripe_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("stripe_event_id", sa.String(255), unique=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("processed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_stripe_events_stripe_event_id", "stripe_events", ["stripe_event_id"])


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")
    postgresql.ENUM(name="notificationtype").drop(op.get_bind(), checkfirst=True)
    op.drop_column("analyses", "share_last_viewed_at")
    op.drop_column("analyses", "share_view_count")
    op.drop_column("organizations", "analyses_used_this_month")
    op.drop_column("organizations", "billing_cycle_start")
    op.drop_column("organizations", "stripe_subscription_id")
    op.drop_column("organizations", "stripe_customer_id")
    # Note: Cannot remove enum value from PostgreSQL — STARTER stays in orgplan enum

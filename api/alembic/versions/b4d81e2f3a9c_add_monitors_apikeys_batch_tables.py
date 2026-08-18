"""Add monitors, api_keys, batch_analyses tables and missing columns.

Revision ID: b4d81e2f3a9c
Revises: a3c72f9e1d4b
Create Date: 2026-03-30 00:00:00.000000

Adds tables and columns that were defined in models.py but missing from migrations:
- monitors table + monitorschedule enum
- monitor_alerts table
- api_keys table
- batch_analyses table
- Missing columns on analyses (share_expires_at, share_password_hash, batch_id)
- Missing column on organizations (free_analyses_remaining)
- 'pptx' value for exportformat enum
- ix_export_jobs_analysis index

To apply:
    cd api && alembic upgrade head

To rollback:
    cd api && alembic downgrade a3c72f9e1d4b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d81e2f3a9c"
down_revision: str | None = "a3c72f9e1d4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Add 'pptx' to exportformat enum ---
    op.execute("ALTER TYPE exportformat ADD VALUE IF NOT EXISTS 'pptx'")

    # --- Create monitorschedule enum ---
    # Explicitly create the enum here, then reference it on the column with
    # ``create_type=False`` so SQLAlchemy does not attempt to auto-create the
    # type a second time during ``op.create_table`` (which would raise
    # ``DuplicateObject`` on a fresh Postgres DB). Mirrors the canonical
    # pattern from a3c72f9e1d4b_add_billing_notifications_models.py.
    monitorschedule_enum = postgresql.ENUM("daily", "weekly", "monthly", name="monitorschedule")
    monitorschedule_enum.create(op.get_bind(), checkfirst=True)

    # --- Add missing columns to organizations ---
    op.add_column(
        "organizations",
        sa.Column("free_analyses_remaining", sa.Integer(), server_default="2", nullable=False),
    )

    # --- Add missing columns to analyses ---
    op.add_column(
        "analyses",
        sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column("share_password_hash", sa.String(255), nullable=True),
    )
    # batch_id FK added after batch_analyses table is created (below)

    # --- Create batch_analyses table ---
    op.create_table(
        "batch_analyses",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), server_default="", nullable=False),
        sa.Column("total_compounds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "running",
                "completed",
                "failed",
                "cancelled",
                "deleted",
                name="analysisstatus",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("analysis_ids", JSONB, server_default="[]", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_batch_analyses_org", "batch_analyses", ["org_id"])

    # Now add batch_id FK to analyses
    op.add_column(
        "analyses",
        sa.Column(
            "batch_id", UUID(as_uuid=True), sa.ForeignKey("batch_analyses.id"), nullable=True
        ),
    )

    # --- Create monitors table ---
    op.create_table(
        "monitors",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("compound_smiles", sa.Text(), nullable=False),
        sa.Column("compound_name", sa.String(500), server_default="", nullable=False),
        sa.Column(
            "schedule",
            postgresql.ENUM(
                "daily", "weekly", "monthly", name="monitorschedule", create_type=False
            ),
            server_default="weekly",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_patent_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cached_patent_ids", JSONB, server_default="[]", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_monitors_org_active", "monitors", ["org_id", "is_active"])

    # --- Create monitor_alerts table ---
    op.create_table(
        "monitor_alerts",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("monitor_id", UUID(as_uuid=True), sa.ForeignKey("monitors.id"), nullable=False),
        sa.Column("new_patent_ids", JSONB, server_default="[]", nullable=False),
        sa.Column("new_patent_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "run_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("dismissed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("dismissed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_monitor_alerts_monitor_dismissed",
        "monitor_alerts",
        ["monitor_id", "dismissed", "created_at"],
    )

    # --- Create api_keys table ---
    op.create_table(
        "api_keys",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_api_keys_org_revoked", "api_keys", ["org_id", "revoked"])

    # --- Add missing index on export_jobs ---
    op.create_index("ix_export_jobs_analysis", "export_jobs", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_export_jobs_analysis", table_name="export_jobs")
    op.drop_index("ix_api_keys_org_revoked", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_monitor_alerts_monitor_dismissed", table_name="monitor_alerts")
    op.drop_table("monitor_alerts")
    op.drop_index("ix_monitors_org_active", table_name="monitors")
    op.drop_table("monitors")
    op.drop_column("analyses", "batch_id")
    op.drop_index("ix_batch_analyses_org", table_name="batch_analyses")
    op.drop_table("batch_analyses")
    op.drop_column("analyses", "share_password_hash")
    op.drop_column("analyses", "share_expires_at")
    op.drop_column("organizations", "free_analyses_remaining")
    postgresql.ENUM(name="monitorschedule").drop(op.get_bind(), checkfirst=True)
    # Note: Cannot remove 'pptx' from exportformat enum in PostgreSQL

"""Initial schema — all tables, indexes, and enum types.

Revision ID: e1b31753ec2c
Revises:
Create Date: 2026-03-19 00:00:00.000000

This migration was generated manually from api/src/api/db/models.py because
no live database was available for autogeneration. It creates all 10 tables,
5 enum types, and 7 composite indexes required by the Praviar platform.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1b31753ec2c"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Enum types ────────────────────────────────────────────────────────────────
# Created explicitly so they are available before table creation and can be
# dropped cleanly on downgrade.

orgplan_enum = postgresql.ENUM("free", "pro", "enterprise", name="orgplan", create_type=False)
userrole_enum = postgresql.ENUM(
    "admin", "attorney", "scientist", "client", name="userrole", create_type=False
)
analysisstatus_enum = postgresql.ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "deleted",
    name="analysisstatus",
    create_type=False,
)
exportformat_enum = postgresql.ENUM(
    "pdf", "docx", "xlsx", "csv", "json", name="exportformat", create_type=False
)
exportstatus_enum = postgresql.ENUM(
    "pending", "processing", "completed", "failed", name="exportstatus", create_type=False
)


def upgrade() -> None:
    # ── Create enum types ─────────────────────────────────────────────────
    orgplan_enum.create(op.get_bind(), checkfirst=True)
    userrole_enum.create(op.get_bind(), checkfirst=True)
    analysisstatus_enum.create(op.get_bind(), checkfirst=True)
    exportformat_enum.create(op.get_bind(), checkfirst=True)
    exportstatus_enum.create(op.get_bind(), checkfirst=True)

    # ── organizations ─────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clerk_org_id", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("plan", orgplan_enum, nullable=False, server_default="free"),
        sa.Column("max_analyses_per_month", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_organizations_clerk_org_id", "organizations", ["clerk_org_id"])

    # ── users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clerk_user_id", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("role", userrole_enum, nullable=False, server_default="scientist"),
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"])

    # ── analyses ──────────────────────────────────────────────────────────
    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        # Input
        sa.Column("compound_input", sa.Text(), nullable=False),
        sa.Column("compound_name", sa.String(500), nullable=False, server_default=""),
        sa.Column("compound_smiles", sa.Text(), nullable=False, server_default=""),
        sa.Column("compound_cid", sa.Integer(), nullable=True),
        sa.Column("input_type", sa.String(20), nullable=False, server_default="name"),
        # Config snapshot (JSONB)
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        # Status
        sa.Column("status", analysisstatus_enum, nullable=False, server_default="pending"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        # Results (JSONB, nullable)
        sa.Column("report_data", postgresql.JSONB(), nullable=True),
        # Summary (denormalized)
        sa.Column("overall_risk", sa.String(20), nullable=True),
        sa.Column("blocking_patents_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_patents_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("executive_summary", sa.Text(), nullable=False, server_default=""),
        # Cost tracking
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pipeline_duration_seconds", sa.Float(), nullable=True),
        # Meta
        sa.Column(
            "initiated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "flagged_for_review", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "flagged_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("share_token", sa.String(64), nullable=True, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_analyses_org_status", "analyses", ["org_id", "status"])
    op.create_index("ix_analyses_org_created", "analyses", ["org_id", "created_at"])
    op.create_index("ix_analyses_compound_smiles", "analyses", ["compound_smiles"])

    # ── compounds ─────────────────────────────────────────────────────────
    op.create_table(
        "compounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_smiles", sa.Text(), nullable=False),
        sa.Column("inchi_key", sa.String(27), nullable=False, unique=True),
        sa.Column("name", sa.String(500), nullable=False, server_default=""),
        sa.Column("molecular_formula", sa.String(200), nullable=False, server_default=""),
        sa.Column("molecular_weight", sa.Float(), nullable=True),
        sa.Column("functional_groups", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("pubchem_cid", sa.Integer(), nullable=True),
        sa.Column(
            "first_analyzed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("analysis_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_compounds_canonical_smiles", "compounds", ["canonical_smiles"])
    op.create_index("ix_compounds_inchi_key", "compounds", ["inchi_key"])
    op.create_index("ix_compounds_pubchem_cid", "compounds", ["pubchem_cid"])

    # ── pipeline_events ───────────────────────────────────────────────────
    op.create_table(
        "pipeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_pipeline_events_analysis", "pipeline_events", ["analysis_id", "created_at"])

    # ── config_presets ────────────────────────────────────────────────────
    op.create_table(
        "config_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # ── comments ──────────────────────────────────────────────────────────
    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("comments.id"), nullable=True
        ),
        sa.Column("target_type", sa.String(50), nullable=False, server_default="analysis"),
        sa.Column("target_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mentions", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        # Legacy escalation columns — dropped by c4e2f7a9b1d6 once comment_thread_escalations exists.
        sa.Column(
            "escalated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_comments_analysis_created", "comments", ["analysis_id", "created_at"])

    # ── attorney_feedback ─────────────────────────────────────────────────
    op.create_table(
        "attorney_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("overall_accuracy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "risk_level_correct", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("corrected_risk", sa.String(20), nullable=True),
        sa.Column("corrections", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # ── audit_logs ────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(45), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["org_id", "created_at"])

    # ── export_jobs ───────────────────────────────────────────────────────
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("format", exportformat_enum, nullable=False),
        sa.Column("status", exportstatus_enum, nullable=False, server_default="pending"),
        sa.Column("file_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("export_jobs")
    op.drop_table("audit_logs")
    op.drop_table("attorney_feedback")
    op.drop_table("comments")
    op.drop_table("config_presets")
    op.drop_table("pipeline_events")
    op.drop_table("compounds")
    op.drop_table("analyses")
    op.drop_table("users")
    op.drop_table("organizations")

    # Drop enum types
    exportstatus_enum.drop(op.get_bind(), checkfirst=True)
    exportformat_enum.drop(op.get_bind(), checkfirst=True)
    analysisstatus_enum.drop(op.get_bind(), checkfirst=True)
    userrole_enum.drop(op.get_bind(), checkfirst=True)
    orgplan_enum.drop(op.get_bind(), checkfirst=True)

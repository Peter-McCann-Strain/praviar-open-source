"""Replace bearer report sharing with recipient-bound grants.

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-07-13 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "y9z0a1b2c3d4"
down_revision: str | Sequence[str] | None = "x8y9z0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing bearer links are deliberately revoked rather than converted:
    # there is no trustworthy recipient identity to bind them to.
    op.execute("DROP POLICY IF EXISTS public_share_token_lookup ON analyses")
    op.drop_column("analyses", "share_password_hash")
    op.drop_column("analyses", "share_expires_at")
    op.drop_column("analyses", "share_token")
    op.add_column(
        "analyses",
        sa.Column("share_active_grant_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "analyses",
        sa.Column("share_active_until", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "external_report_grants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column("recipient_email_normalized", sa.String(320), nullable=False),
        sa.Column("recipient_domain", sa.String(255), nullable=False),
        sa.Column("grant_token_hash", sa.String(64), nullable=False),
        sa.Column("report_fingerprint", sa.String(64), nullable=False),
        sa.Column("invitation_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_code_hash", sa.String(255), nullable=True),
        sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("access_secret_hash", sa.String(64), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_views", sa.Integer(), server_default="25", nullable=False),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("download_allowed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("max_downloads", sa.Integer(), server_default="0", nullable=False),
        sa.Column("download_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("max_views > 0", name="ck_external_report_grants_max_views_positive"),
        sa.CheckConstraint(
            "view_count >= 0 AND view_count <= max_views",
            name="ck_external_report_grants_view_count_range",
        ),
        sa.CheckConstraint(
            "max_downloads >= 0 AND download_count >= 0 AND download_count <= max_downloads",
            name="ck_external_report_grants_download_count_range",
        ),
        sa.UniqueConstraint("grant_token_hash", name="uq_external_report_grants_token_hash"),
    )
    op.create_index(
        "ix_external_report_grants_org_analysis",
        "external_report_grants",
        ["org_id", "analysis_id"],
    )
    op.create_index(
        "ix_external_report_grants_analysis_recipient",
        "external_report_grants",
        ["analysis_id", "recipient_email_normalized"],
    )
    op.create_index(
        "ix_external_report_grants_expires",
        "external_report_grants",
        ["expires_at"],
    )
    op.execute("ALTER TABLE external_report_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE external_report_grants FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_isolation ON external_report_grants
        USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY public_grant_lookup ON external_report_grants
        FOR SELECT
        USING (
            grant_token_hash = current_setting('app.public_share_grant_hash', true)
        )
        """
    )
    op.execute(
        """
        CREATE POLICY public_grant_update ON external_report_grants
        FOR UPDATE
        USING (
            grant_token_hash = current_setting('app.public_share_grant_hash', true)
        )
        WITH CHECK (
            grant_token_hash = current_setting('app.public_share_grant_hash', true)
        )
        """
    )


def downgrade() -> None:
    op.drop_table("external_report_grants")
    op.drop_column("analyses", "share_active_until")
    op.drop_column("analyses", "share_active_grant_count")
    op.add_column("analyses", sa.Column("share_token", sa.String(64), nullable=True))
    op.add_column(
        "analyses", sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("analyses", sa.Column("share_password_hash", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_analyses_share_token", "analyses", ["share_token"])
    op.execute(
        """
        CREATE POLICY public_share_token_lookup ON analyses
        FOR SELECT
        USING (
            share_token IS NOT NULL
            AND share_token = current_setting('app.public_share_token', true)
        )
        """
    )

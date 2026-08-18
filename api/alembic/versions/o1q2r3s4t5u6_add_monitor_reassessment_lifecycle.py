"""Add durable counsel reassessment and artifact supersession lifecycle.

Revision ID: o1q2r3s4t5u6
Revises: n0p1q2r3s4t5
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "o1q2r3s4t5u6"
down_revision: str | Sequence[str] | None = "n0p1q2r3s4t5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def upgrade() -> None:
    op.drop_constraint("ck_monitors_conclusion_status", "monitors", type_="check")
    op.create_check_constraint(
        "ck_monitors_conclusion_status",
        "monitors",
        "conclusion_status IN ('unbound', 'fresh', 'review_required', 'reassessed')",
    )

    op.add_column(
        "export_jobs",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "export_jobs",
        sa.Column("superseded_reason", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "export_jobs",
        sa.Column(
            "superseded_conclusion_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "monitor_conclusion_reassessments",
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
            "monitor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monitors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_report_id", sa.String(length=100), server_default="", nullable=False),
        sa.Column("conclusion_id", sa.String(length=160), nullable=False),
        sa.Column("conclusion_type", sa.String(length=64), nullable=False),
        sa.Column("conclusion_label", sa.String(length=500), nullable=False),
        sa.Column("previous_outcome", sa.String(length=100), server_default="", nullable=False),
        sa.Column("dependency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="open", nullable=False),
        sa.Column(
            "trigger_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "invalidated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "latest_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewer_role", sa.String(length=32), server_default="", nullable=False),
        sa.Column("reviewer_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("reviewer_email", sa.String(length=255), server_default="", nullable=False),
        sa.Column("resolution_note", sa.Text(), server_default="", nullable=False),
        sa.Column("attestation_version", sa.String(length=32), server_default="", nullable=False),
        sa.Column("attestation_statement", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "attestation_accepted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "replacement_analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'reaffirmed', 'superseded', 'withdrawn')",
            name="ck_monitor_conclusion_reassessments_status",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL "
            "AND resolved_by_user_id IS NULL AND attestation_accepted = false "
            "AND reviewer_role = '' AND reviewer_name = '' AND reviewer_email = '' "
            "AND resolution_note = '' AND attestation_version = '' "
            "AND attestation_statement = '' AND replacement_analysis_id IS NULL) OR "
            "(status <> 'open' AND resolved_at IS NOT NULL "
            "AND attestation_accepted = true "
            "AND reviewer_role = 'attorney' "
            "AND length(btrim(reviewer_name)) > 0 "
            "AND length(btrim(reviewer_email)) > 0 "
            "AND length(btrim(resolution_note)) >= 20 "
            "AND length(btrim(attestation_version)) > 0 "
            "AND length(btrim(attestation_statement)) > 0)",
            name="ck_monitor_conclusion_reassessments_resolution",
        ),
        sa.CheckConstraint(
            "length(btrim(conclusion_id)) > 0 "
            "AND length(btrim(conclusion_type)) > 0 "
            "AND length(btrim(conclusion_label)) > 0 "
            "AND dependency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_monitor_conclusion_reassessments_identity",
        ),
        sa.CheckConstraint(
            "latest_observed_at >= invalidated_at "
            "AND (resolved_at IS NULL OR resolved_at >= invalidated_at)",
            name="ck_monitor_conclusion_reassessments_chronology",
        ),
    )
    op.create_index(
        "ix_monitor_conclusion_reassessments_org_analysis_status",
        "monitor_conclusion_reassessments",
        ["org_id", "source_analysis_id", "status"],
    )
    op.create_index(
        "ix_monitor_conclusion_reassessments_org_monitor_status",
        "monitor_conclusion_reassessments",
        ["org_id", "monitor_id", "status"],
    )
    # Preserve invalidations created between the conclusion-aware rollout and
    # this durable lifecycle migration. Malformed legal state must halt the
    # migration for operator remediation instead of being silently omitted.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM monitors
                 WHERE jsonb_typeof(stale_conclusions) <> 'array'
            ) THEN
                RAISE EXCEPTION
                    'Cannot migrate malformed monitor stale_conclusions: expected JSON arrays';
            END IF;
            IF EXISTS (
                SELECT 1
                  FROM monitors
                 WHERE source_analysis_id IS NULL
                   AND jsonb_array_length(stale_conclusions) > 0
            ) THEN
                RAISE EXCEPTION
                    'Cannot migrate stale conclusions without a source analysis';
            END IF;
            IF EXISTS (
                SELECT 1
                  FROM monitors
                  CROSS JOIN LATERAL
                    jsonb_array_elements(stale_conclusions) AS impact
                 WHERE length(btrim(COALESCE(impact ->> 'conclusion_id', ''))) = 0
                    OR length(
                        btrim(COALESCE(
                            impact ->> 'conclusion_type',
                            'report_conclusion'
                        ))
                    ) = 0
                    OR length(
                        btrim(COALESCE(
                            impact ->> 'label',
                            impact ->> 'conclusion_id',
                            ''
                        ))
                    ) = 0
                    OR COALESCE(impact ->> 'dependency_fingerprint', '')
                        !~ '^[0-9a-f]{64}$'
            ) THEN
                RAISE EXCEPTION
                    'Cannot migrate malformed monitor conclusion identity provenance';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        INSERT INTO monitor_conclusion_reassessments (
            org_id,
            monitor_id,
            source_analysis_id,
            source_report_id,
            conclusion_id,
            conclusion_type,
            conclusion_label,
            previous_outcome,
            dependency_fingerprint,
            status,
            trigger_evidence,
            invalidated_at,
            latest_observed_at
        )
        SELECT DISTINCT ON (
            monitors.org_id,
            monitors.id,
            impact ->> 'conclusion_id'
        )
            monitors.org_id,
            monitors.id,
            monitors.source_analysis_id,
            COALESCE(impact ->> 'source_report_id', monitors.source_report_id, ''),
            impact ->> 'conclusion_id',
            COALESCE(impact ->> 'conclusion_type', 'report_conclusion'),
            COALESCE(impact ->> 'label', impact ->> 'conclusion_id'),
            COALESCE(impact ->> 'previous_outcome', ''),
            impact ->> 'dependency_fingerprint',
            'open',
            impact,
            COALESCE(NULLIF(impact ->> 'invalidated_at', '')::timestamptz, now()),
            COALESCE(NULLIF(impact ->> 'latest_observed_at', '')::timestamptz, now())
        FROM monitors
        CROSS JOIN LATERAL jsonb_array_elements(monitors.stale_conclusions) AS impact
        WHERE monitors.source_analysis_id IS NOT NULL
        ORDER BY
            monitors.org_id,
            monitors.id,
            impact ->> 'conclusion_id',
            COALESCE(NULLIF(impact ->> 'latest_observed_at', '')::timestamptz, now()) DESC
        """
    )
    op.create_index(
        "uq_monitor_conclusion_reassessments_open_episode",
        "monitor_conclusion_reassessments",
        ["org_id", "monitor_id", "conclusion_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND monitor_id IS NOT NULL"),
    )
    # Every copied tenant key must agree with its referenced rows, including
    # writes made by the BYPASSRLS monitor worker. RLS alone cannot prove this
    # relationship because globally unique UUIDs still permit a mismatched
    # org_id to be copied onto a valid foreign key.
    op.execute(
        """
        CREATE FUNCTION public.validate_monitor_conclusion_reassessment_org()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM public.analyses
                 WHERE id = NEW.source_analysis_id
                   AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION
                    'monitor reassessment source analysis belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.monitor_id IS NOT NULL AND NOT EXISTS (
                SELECT 1
                  FROM public.monitors
                 WHERE id = NEW.monitor_id
                   AND org_id = NEW.org_id
                   AND source_analysis_id = NEW.source_analysis_id
            ) THEN
                RAISE EXCEPTION
                    'monitor reassessment watch does not match its organization and source analysis'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.resolved_by_user_id IS NOT NULL AND NOT EXISTS (
                SELECT 1
                  FROM public.users
                 WHERE id = NEW.resolved_by_user_id
                   AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION
                    'monitor reassessment reviewer belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.replacement_analysis_id IS NOT NULL AND NOT EXISTS (
                SELECT 1
                  FROM public.analyses
                 WHERE id = NEW.replacement_analysis_id
                   AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION
                    'monitor reassessment replacement analysis belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_monitor_conclusion_reassessment_org_guard
            BEFORE INSERT OR UPDATE OF
                org_id,
                monitor_id,
                source_analysis_id,
                resolved_by_user_id,
                replacement_analysis_id
            ON monitor_conclusion_reassessments
            FOR EACH ROW
            EXECUTE FUNCTION public.validate_monitor_conclusion_reassessment_org();
        """
    )
    op.execute("ALTER TABLE monitor_conclusion_reassessments ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE monitor_conclusion_reassessments FORCE ROW LEVEL SECURITY;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON monitor_conclusion_reassessments
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def downgrade() -> None:
    # A legal-attestation ledger must never disappear as an incidental schema
    # rollback. Operators must explicitly archive/remediate rows first.
    op.execute("ALTER TABLE monitor_conclusion_reassessments NO FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM monitor_conclusion_reassessments) THEN
                EXECUTE
                    'ALTER TABLE monitor_conclusion_reassessments FORCE ROW LEVEL SECURITY';
                RAISE EXCEPTION
                    'Refusing to downgrade while monitor conclusion reassessments remain';
            END IF;
        EXCEPTION WHEN OTHERS THEN
            EXECUTE
                'ALTER TABLE monitor_conclusion_reassessments FORCE ROW LEVEL SECURITY';
            RAISE;
        END
        $$;
        """
    )
    op.execute("DROP POLICY IF EXISTS org_isolation ON monitor_conclusion_reassessments;")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_monitor_conclusion_reassessment_org_guard "
        "ON monitor_conclusion_reassessments;"
    )
    op.execute("DROP FUNCTION IF EXISTS public.validate_monitor_conclusion_reassessment_org();")
    op.drop_table("monitor_conclusion_reassessments")
    op.drop_column("export_jobs", "superseded_conclusion_ids")
    op.drop_column("export_jobs", "superseded_reason")
    op.drop_column("export_jobs", "superseded_at")
    op.drop_constraint("ck_monitors_conclusion_status", "monitors", type_="check")
    op.execute(
        """
        UPDATE monitors
           SET conclusion_status = 'fresh'
         WHERE conclusion_status = 'reassessed'
        """
    )
    op.create_check_constraint(
        "ck_monitors_conclusion_status",
        "monitors",
        "conclusion_status IN ('unbound', 'fresh', 'review_required')",
    )

"""Add case-scoped, query-plan-bound patent relevance feedback.

Revision ID: p2q3r4s5t6u7
Revises: o1q2r3s4t5u6
Create Date: 2026-07-26 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "p2q3r4s5t6u7"
down_revision: str | Sequence[str] | None = "o1q2r3s4t5u6"
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
    op.create_table(
        "analysis_search_relevance_feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("patent_id", sa.String(length=64), nullable=False),
        sa.Column("relevance", sa.String(length=24), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "suggested_queries",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("query_plan_sha256", sa.String(length=64), nullable=False),
        sa.Column("report_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "reviewer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("reviewer_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("reviewer_email", sa.String(length=255), server_default="", nullable=False),
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
            "relevance IN ('relevant', 'not_relevant', 'uncertain')",
            name="ck_analysis_search_relevance_feedback_label",
        ),
        sa.CheckConstraint(
            "query_plan_sha256 ~ '^[0-9a-f]{64}$' "
            "AND report_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_search_relevance_feedback_fingerprints",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array' "
            "AND jsonb_typeof(suggested_queries) = 'array'",
            name="ck_analysis_search_relevance_feedback_json_arrays",
        ),
        sa.CheckConstraint(
            "length(btrim(patent_id)) > 0",
            name="ck_analysis_search_relevance_feedback_patent_id",
        ),
    )
    op.create_index(
        "ix_analysis_search_relevance_feedback_org_analysis",
        "analysis_search_relevance_feedback",
        ["org_id", "analysis_id"],
    )
    op.create_index(
        "uq_analysis_search_relevance_feedback_reviewer_patent",
        "analysis_search_relevance_feedback",
        ["analysis_id", "patent_id", "reviewer_user_id"],
        unique=True,
    )

    # The guard protects writes by both tenant-scoped API roles and BYPASSRLS
    # workers. It binds every label to the current report's exact query-plan
    # digest and search funnel, not merely to a globally unique analysis UUID.
    op.execute(
        """
        CREATE FUNCTION public.validate_search_relevance_feedback_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM public.analyses AS analysis
                 WHERE analysis.id = NEW.analysis_id
                   AND analysis.org_id = NEW.org_id
                   AND analysis.status::text = 'completed'
                   AND analysis.report_data #>> '{audit_trail,query_plan,plan_sha256}'
                       = NEW.query_plan_sha256
                   AND EXISTS (
                       SELECT 1
                         FROM jsonb_array_elements(
                             COALESCE(
                                 analysis.report_data #> '{audit_trail,search_funnel}',
                                 '[]'::jsonb
                             )
                         ) AS funnel_entry
                        WHERE funnel_entry ->> 'patent_id' = NEW.patent_id
                   )
            ) THEN
                RAISE EXCEPTION
                    'search relevance feedback is outside the current governed query plan'
                    USING ERRCODE = '23514';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                  FROM public.users AS reviewer
                 WHERE reviewer.id = NEW.reviewer_user_id
                   AND reviewer.org_id = NEW.org_id
                   AND reviewer.role::text IN ('admin', 'attorney')
                   AND reviewer.membership_active = true
                   AND reviewer.membership_deleted_at IS NULL
                   AND reviewer.membership_permission_denied_at IS NULL
            ) THEN
                RAISE EXCEPTION
                    'search relevance reviewer lacks current authority in the organization'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_search_relevance_feedback_scope_guard
            BEFORE INSERT OR UPDATE OF
                analysis_id,
                org_id,
                patent_id,
                query_plan_sha256,
                reviewer_user_id
            ON analysis_search_relevance_feedback
            FOR EACH ROW
            EXECUTE FUNCTION public.validate_search_relevance_feedback_scope();
        """
    )
    op.execute("ALTER TABLE analysis_search_relevance_feedback ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE analysis_search_relevance_feedback FORCE ROW LEVEL SECURITY;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON analysis_search_relevance_feedback
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE analysis_search_relevance_feedback NO FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM analysis_search_relevance_feedback) THEN
                EXECUTE
                    'ALTER TABLE analysis_search_relevance_feedback FORCE ROW LEVEL SECURITY';
                RAISE EXCEPTION
                    'Refusing to downgrade while search relevance feedback remains';
            END IF;
        EXCEPTION WHEN OTHERS THEN
            EXECUTE
                'ALTER TABLE analysis_search_relevance_feedback FORCE ROW LEVEL SECURITY';
            RAISE;
        END
        $$;
        """
    )
    op.execute(
        "DROP POLICY IF EXISTS org_isolation ON analysis_search_relevance_feedback;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_search_relevance_feedback_scope_guard "
        "ON analysis_search_relevance_feedback;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.validate_search_relevance_feedback_scope();"
    )
    op.drop_table("analysis_search_relevance_feedback")

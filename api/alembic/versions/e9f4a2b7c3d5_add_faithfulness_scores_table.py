"""Add faithfulness_scores table for T3-02 shadow-mode UQ signal.

Revision ID: e9f4a2b7c3d5
Revises: a1b2c3d4e5f6
Create Date: 2026-05-20 12:00:00.000000

Adds the ``faithfulness_scores`` table that captures per-(claim sentence,
evidence span) entailment verdicts emitted by the Faithfulness-Aware UQ
scorer. Shadow mode: the rows here never influence reviewer queue ordering
or report assembly until correlation with reviewer-override events has been
measured. See:
  - Paper: arXiv:2505.21072 (Vashurin, Fadeeva et al., May 2025)
  - Plan item: T3-02 in .claude/upgrade-plan.md
  - Feature flag: PRAVIAR_FAITHFULNESS_UQ_ENABLED
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9f4a2b7c3d5"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_ORG_ISOLATION_POLICY_SQL = """
CREATE POLICY org_isolation ON faithfulness_scores
    FOR ALL
    USING (
        org_id = (
            CASE
                WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                THEN current_setting('app.current_org_id', true)::uuid
                ELSE NULL::uuid
            END
        )
    )
    WITH CHECK (
        org_id = (
            CASE
                WHEN current_setting('app.current_org_id', true) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                THEN current_setting('app.current_org_id', true)::uuid
                ELSE NULL::uuid
            END
        )
    );
"""


def upgrade() -> None:
    op.create_table(
        "faithfulness_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("finding_index", sa.Integer(), nullable=False),
        sa.Column("evidence_index", sa.Integer(), nullable=False),
        sa.Column("claim_sentence", sa.Text(), nullable=False),
        sa.Column("evidence_span", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("model_id", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_faithfulness_scores_analysis",
        "faithfulness_scores",
        ["analysis_id"],
    )
    op.create_index(
        "ix_faithfulness_scores_org",
        "faithfulness_scores",
        ["org_id"],
    )
    op.create_index(
        "ix_faithfulness_scores_analysis_finding",
        "faithfulness_scores",
        ["analysis_id", "finding_index", "evidence_index"],
    )

    # RLS does not propagate through foreign keys. Enable isolation explicitly
    # so faithfulness_scores obeys the same org-scoped policy as analyses.
    op.execute("ALTER TABLE faithfulness_scores ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faithfulness_scores FORCE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS org_isolation ON faithfulness_scores;")
    op.execute(CREATE_ORG_ISOLATION_POLICY_SQL)


def downgrade() -> None:
    op.drop_index(
        "ix_faithfulness_scores_analysis_finding",
        table_name="faithfulness_scores",
    )
    op.drop_index("ix_faithfulness_scores_org", table_name="faithfulness_scores")
    op.drop_index("ix_faithfulness_scores_analysis", table_name="faithfulness_scores")
    op.execute("DROP POLICY IF EXISTS org_isolation ON faithfulness_scores;")
    op.execute("ALTER TABLE faithfulness_scores NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE faithfulness_scores DISABLE ROW LEVEL SECURITY;")
    op.drop_table("faithfulness_scores")

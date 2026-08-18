"""Add unique constraint on faithfulness_scores (analysis_id, finding_index, evidence_index, model_id).

Prevents duplicate (claim, evidence, model) rows on Celery at-least-once redelivery.
The advisory lock only guards concurrent execution; the unique constraint closes the
sequential-redelivery window where two deliveries of the same task both pass the
pre-insert count check before either commits.

Revision ID: q1l2m3n4o5p6
Revises: p0k1l2m3n4o5
Create Date: 2026-06-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "q1l2m3n4o5p6"
down_revision: str | Sequence[str] | None = "p0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The constraint exists precisely because at-least-once Celery redelivery
    # could write duplicate (analysis_id, finding_index, evidence_index,
    # model_id) rows before it existed. ADD CONSTRAINT validates against current
    # data, so on any production table that already accumulated such duplicates
    # this migration would abort the deploy. Collapse pre-existing duplicates
    # first, keeping the most recent row (newest created_at, tie-broken by id)
    # so the surviving score reflects the latest evaluation. The DELETE is a
    # no-op on a table that has no duplicates.
    op.execute(
        sa.text(
            """
            DELETE FROM faithfulness_scores fs
            USING faithfulness_scores keep
            WHERE fs.analysis_id = keep.analysis_id
              AND fs.finding_index = keep.finding_index
              AND fs.evidence_index = keep.evidence_index
              AND fs.model_id = keep.model_id
              AND (fs.created_at, fs.id) < (keep.created_at, keep.id)
            """
        )
    )
    op.create_unique_constraint(
        "uq_faithfulness_scores_analysis_pair_model",
        "faithfulness_scores",
        ["analysis_id", "finding_index", "evidence_index", "model_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_faithfulness_scores_analysis_pair_model",
        "faithfulness_scores",
        type_="unique",
    )

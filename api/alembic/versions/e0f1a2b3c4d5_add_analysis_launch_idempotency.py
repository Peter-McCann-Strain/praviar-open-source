"""Add durable analysis-launch idempotency and submitted identity provenance.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-07-17 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ECMASCRIPT_TRIM_SQL = (
    "chr(9) || chr(10) || chr(11) || chr(12) || chr(13) || chr(32) || "
    "chr(160) || chr(5760) || chr(8192) || chr(8193) || chr(8194) || "
    "chr(8195) || chr(8196) || chr(8197) || chr(8198) || chr(8199) || "
    "chr(8200) || chr(8201) || chr(8202) || chr(8232) || chr(8233) || "
    "chr(8239) || chr(8287) || chr(12288) || chr(65279)"
)
_CAS_INPUT_REGEX_SQL = (
    "'^([Cc][Aa][Ss]([' || "
    f"{_ECMASCRIPT_TRIM_SQL} || "
    "']*([Rr][Nn]|[Nn][Oo]\\.?|#|:))?[' || "
    f"{_ECMASCRIPT_TRIM_SQL} || "
    "']*)?[0-9]{2,7}-[0-9]{2}-[0-9]$'"
)
_ECMASCRIPT_WHITESPACE_REGEX_SQL = f"'[' || {_ECMASCRIPT_TRIM_SQL} || ']'"


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "submitted_identity_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "analyses",
        sa.Column("submitted_identity_value", sa.Text(), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column("launch_idempotency_key_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column("launch_payload_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "pipeline_reconciliation_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "pipeline_reconciliation_dispatched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Historical rows predate authoritative submitted-input typing. Normalize
    # them with the same ordered syntax classifier used by the request model
    # before installing the exact database invariant.
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"UPDATE analyses SET compound_input = btrim(compound_input, {_ECMASCRIPT_TRIM_SQL})"
    )
    op.execute(
        "UPDATE analyses SET input_type = CASE "
        f"WHEN compound_input ~ ({_CAS_INPUT_REGEX_SQL}) "
        "THEN 'cas' "
        "WHEN compound_input LIKE 'InChI=%' THEN 'inchi' "
        "WHEN compound_input ~ '^[A-Za-z]{14}-[A-Za-z]{10}-[A-Za-z]$' "
        "THEN 'inchikey' "
        f"WHEN compound_input !~ ({_ECMASCRIPT_WHITESPACE_REGEX_SQL}) "
        "AND compound_input ~ "
        "'^(\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|"
        "[-=#$:/\\\\.()]|%[0-9]{2}|[1-9]|\\*)+$' "
        "AND (regexp_count(compound_input, "
        "'\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|\\*') >= 2 "
        "OR (regexp_count(compound_input, "
        "'\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|\\*') = 1 "
        "AND compound_input ~ "
        "'\\[[^]]*\\]|\\*|[-=#$:/\\\\.()]|%[0-9]{2}|[1-9]')) "
        "THEN 'smiles' "
        "ELSE 'name' END"
    )

    op.create_check_constraint(
        "ck_analyses_submitted_input_type",
        "analyses",
        "input_type IN ('name', 'smiles', 'cas', 'inchi', 'inchikey')",
    )
    op.create_check_constraint(
        "ck_analyses_compound_input_normalized",
        "analyses",
        f"compound_input = btrim(compound_input, {_ECMASCRIPT_TRIM_SQL})",
    )
    op.create_check_constraint(
        "ck_analyses_submitted_input_type_matches_value",
        "analyses",
        "input_type = CASE "
        f"WHEN compound_input ~ ({_CAS_INPUT_REGEX_SQL}) "
        "THEN 'cas' "
        "WHEN compound_input LIKE 'InChI=%' THEN 'inchi' "
        "WHEN compound_input ~ '^[A-Za-z]{14}-[A-Za-z]{10}-[A-Za-z]$' "
        "THEN 'inchikey' "
        f"WHEN compound_input !~ ({_ECMASCRIPT_WHITESPACE_REGEX_SQL}) "
        "AND compound_input ~ "
        "'^(\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|"
        "[-=#$:/\\\\.()]|%[0-9]{2}|[1-9]|\\*)+$' "
        "AND (regexp_count(compound_input, "
        "'\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|\\*') >= 2 "
        "OR (regexp_count(compound_input, "
        "'\\[[^]]*\\]|Cl|Br|[BCNOPSFIbcnops]|\\*') = 1 "
        "AND compound_input ~ "
        "'\\[[^]]*\\]|\\*|[-=#$:/\\\\.()]|%[0-9]{2}|[1-9]')) "
        "THEN 'smiles' "
        "ELSE 'name' END",
    )
    op.create_check_constraint(
        "ck_analyses_submitted_identity_confirmation",
        "analyses",
        "(submitted_identity_confirmed AND "
        "submitted_identity_value IS NOT NULL AND "
        "submitted_identity_value = compound_input) OR "
        "(NOT submitted_identity_confirmed AND submitted_identity_value IS NULL)",
    )
    op.create_check_constraint(
        "ck_analyses_launch_idempotency_pair",
        "analyses",
        "(launch_idempotency_key_digest IS NULL AND launch_payload_digest IS NULL) OR "
        "(launch_idempotency_key_digest IS NOT NULL "
        "AND launch_payload_digest IS NOT NULL "
        "AND launch_idempotency_key_digest ~ '^[0-9a-f]{64}$' "
        "AND launch_payload_digest ~ '^[0-9a-f]{64}$')",
    )
    op.create_check_constraint(
        "ck_analyses_pipeline_reconciliation_generation",
        "analyses",
        "pipeline_reconciliation_generation >= 0",
    )
    op.create_index(
        "uq_analyses_org_launch_idempotency",
        "analyses",
        ["org_id", "launch_idempotency_key_digest"],
        unique=True,
        postgresql_where=sa.text("launch_idempotency_key_digest IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_analyses_org_launch_idempotency",
        table_name="analyses",
    )
    op.drop_constraint(
        "ck_analyses_pipeline_reconciliation_generation",
        "analyses",
        type_="check",
    )
    op.drop_constraint(
        "ck_analyses_launch_idempotency_pair",
        "analyses",
        type_="check",
    )
    op.drop_constraint(
        "ck_analyses_submitted_identity_confirmation",
        "analyses",
        type_="check",
    )
    op.drop_constraint(
        "ck_analyses_submitted_input_type_matches_value",
        "analyses",
        type_="check",
    )
    op.drop_constraint(
        "ck_analyses_compound_input_normalized",
        "analyses",
        type_="check",
    )
    op.drop_constraint(
        "ck_analyses_submitted_input_type",
        "analyses",
        type_="check",
    )
    op.drop_column("analyses", "launch_payload_digest")
    op.drop_column("analyses", "launch_idempotency_key_digest")
    op.drop_column("analyses", "pipeline_reconciliation_dispatched_at")
    op.drop_column("analyses", "pipeline_reconciliation_generation")
    op.drop_column("analyses", "submitted_identity_value")
    op.drop_column("analyses", "submitted_identity_confirmed")

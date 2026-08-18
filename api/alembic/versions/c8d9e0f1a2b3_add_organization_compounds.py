"""Add organization-local compound usage metadata.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-16 23:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ORG_CONTEXT_UUID_EXPR = """(
    CASE
        WHEN current_setting('app.current_org_id', true)
            ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN current_setting('app.current_org_id', true)::uuid
        ELSE NULL::uuid
    END
)"""


def upgrade() -> None:
    op.create_table(
        "organization_compounds",
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "compound_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("compounds.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "display_name",
            sa.String(length=500),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "first_analyzed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "analysis_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.CheckConstraint(
            "analysis_count > 0",
            name="ck_organization_compounds_analysis_count_positive",
        ),
    )
    op.create_index(
        "ix_organization_compounds_org_first",
        "organization_compounds",
        ["org_id", sa.text("first_analyzed_at DESC"), "compound_id"],
        unique=False,
    )

    # analyses already has FORCE RLS. The migration owner needs a bounded
    # owner-visible window to backfill every organization in one transaction.
    # ENABLE remains in force, so non-owner application roles remain isolated.
    op.execute("ALTER TABLE analyses NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        WITH completed_identities AS (
            SELECT
                a.id AS analysis_id,
                a.completed_at,
                COALESCE(
                    NULLIF(trim(a.report_data #>> '{compound,compound_type}'), ''),
                    'small_molecule'
                ) AS compound_type,
                NULLIF(trim(a.report_data #>> '{compound,inchi_key}'), '') AS inchi_key,
                COALESCE(
                    NULLIF(trim(a.report_data #>> '{compound,canonical_smiles}'), ''),
                    NULLIF(trim(a.compound_smiles), ''),
                    ''
                ) AS canonical_smiles,
                left(
                    COALESCE(
                        NULLIF(trim(a.report_data #>> '{compound,molecular_formula}'), ''),
                        ''
                    ),
                    200
                ) AS molecular_formula
            FROM analyses AS a
            WHERE a.status = 'completed'
        ),
        ranked_identities AS (
            SELECT
                completed_identities.*,
                row_number() OVER (
                    PARTITION BY inchi_key
                    ORDER BY completed_at DESC, analysis_id DESC
                ) AS identity_rank,
                count(*) OVER (
                    PARTITION BY inchi_key
                ) AS identity_analysis_count,
                min(completed_at) OVER (
                    PARTITION BY inchi_key
                ) AS first_analyzed_at
            FROM completed_identities
            WHERE compound_type IN ('small_molecule', 'biologic', 'peptide')
              AND inchi_key ~ '^[A-Z]{14}-[A-Z]{10}-[A-Z]$'
        )
        INSERT INTO compounds (
            id,
            canonical_smiles,
            inchi_key,
            name,
            molecular_formula,
            functional_groups,
            first_analyzed_at,
            analysis_count
        )
        SELECT
            md5('praviar-compound:' || inchi_key)::uuid,
            canonical_smiles,
            inchi_key,
            '',
            molecular_formula,
            '[]'::jsonb,
            first_analyzed_at,
            identity_analysis_count::integer
        FROM ranked_identities
        WHERE identity_rank = 1
        ON CONFLICT (inchi_key) DO NOTHING
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                WITH completed_identities AS (
                    SELECT
                        COALESCE(
                            NULLIF(
                                trim(a.report_data #>> '{compound,compound_type}'),
                                ''
                            ),
                            'small_molecule'
                        ) AS compound_type,
                        NULLIF(
                            trim(a.report_data #>> '{compound,inchi_key}'),
                            ''
                        ) AS inchi_key,
                        COALESCE(
                            NULLIF(
                                trim(
                                    a.report_data
                                    #>> '{compound,canonical_smiles}'
                                ),
                                ''
                            ),
                            NULLIF(trim(a.compound_smiles), '')
                        ) AS canonical_smiles
                    FROM analyses AS a
                    WHERE a.status = 'completed'
                )
                SELECT 1
                FROM completed_identities
                WHERE compound_type NOT IN (
                    'small_molecule',
                    'biologic',
                    'peptide'
                )
                   OR (
                        inchi_key IS NOT NULL
                        AND inchi_key !~ '^[A-Z]{14}-[A-Z]{10}-[A-Z]$'
                   )
                   OR (
                        compound_type = 'small_molecule'
                        AND inchi_key IS NULL
                        AND (
                            canonical_smiles IS NULL
                            OR (
                                SELECT count(*)
                                FROM compounds AS c
                                WHERE c.canonical_smiles =
                                    completed_identities.canonical_smiles
                            ) <> 1
                        )
                   )
            ) THEN
                RAISE EXCEPTION
                    'Cannot backfill organization_compounds: completed analysis '
                    'has an unsupported, malformed, or ambiguous compound identity';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        WITH resolved_analysis_compounds AS (
            SELECT
                a.org_id,
                a.completed_at,
                COALESCE(
                    NULLIF(trim(a.report_data #>> '{compound,compound_type}'), ''),
                    'small_molecule'
                ) AS compound_type,
                NULLIF(trim(a.report_data #>> '{compound,inchi_key}'), '') AS inchi_key,
                COALESCE(
                    NULLIF(trim(a.report_data #>> '{compound,canonical_smiles}'), ''),
                    NULLIF(trim(a.compound_smiles), '')
                ) AS canonical_smiles,
                left(
                    COALESCE(
                        NULLIF(trim(a.report_data #>> '{compound,name}'), ''),
                        NULLIF(trim(a.compound_name), ''),
                        ''
                    ),
                    500
                ) AS display_name,
                COALESCE(
                    (
                        SELECT c.id
                        FROM compounds AS c
                        WHERE c.inchi_key =
                            NULLIF(trim(a.report_data #>> '{compound,inchi_key}'), '')
                    ),
                    (
                        SELECT c.id
                        FROM compounds AS c
                        WHERE COALESCE(
                            NULLIF(
                                trim(a.report_data #>> '{compound,compound_type}'),
                                ''
                            ),
                            'small_molecule'
                        ) = 'small_molecule'
                          AND c.canonical_smiles = COALESCE(
                              NULLIF(
                                  trim(
                                      a.report_data
                                      #>> '{compound,canonical_smiles}'
                                  ),
                                  ''
                              ),
                              NULLIF(trim(a.compound_smiles), '')
                          )
                          AND (
                              SELECT count(*)
                              FROM compounds AS matching
                              WHERE matching.canonical_smiles = COALESCE(
                                  NULLIF(
                                      trim(
                                          a.report_data
                                          #>> '{compound,canonical_smiles}'
                                      ),
                                      ''
                                  ),
                                  NULLIF(trim(a.compound_smiles), '')
                              )
                          ) = 1
                        LIMIT 1
                    )
                ) AS compound_id
            FROM analyses AS a
            WHERE a.status = 'completed'
        )
        INSERT INTO organization_compounds (
            org_id,
            compound_id,
            display_name,
            first_analyzed_at,
            analysis_count
        )
        SELECT
            org_id,
            compound_id,
            COALESCE(
                (
                    array_agg(display_name ORDER BY completed_at DESC)
                    FILTER (WHERE display_name <> '')
                )[1],
                ''
            ),
            min(completed_at),
            count(*)::integer
        FROM resolved_analysis_compounds
        WHERE compound_id IS NOT NULL
        GROUP BY org_id, compound_id
        """
    )
    # The legacy global table could contain a tenant-supplied project label.
    # Display labels now live only on the RLS-protected association, so erase
    # them from every identity that participates in an organization library.
    op.execute(
        """
        UPDATE compounds AS c
        SET name = ''
        WHERE EXISTS (
            SELECT 1
            FROM organization_compounds AS oc
            WHERE oc.compound_id = c.id
        )
        """
    )
    op.execute("ALTER TABLE analyses FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE organization_compounds ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organization_compounds FORCE ROW LEVEL SECURITY")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON organization_compounds
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR})
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organization_compounds NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS org_isolation ON organization_compounds")
    op.drop_index(
        "ix_organization_compounds_org_first",
        table_name="organization_compounds",
    )
    op.drop_table("organization_compounds")

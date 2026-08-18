"""Harden credit ledger invariants and API-key lookup capability.

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-07-11 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "x8y9z0a1b2c3"
down_revision: str | Sequence[str] | None = "w7x8y9z0a1b2"
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
    # Existing pre-namespace credentials cannot meet the new fail-closed shape
    # contract. Revoke them explicitly instead of leaving an undocumented
    # compatibility authentication path.
    #
    # PostgreSQL will not alter a column while an RLS policy or index depends on
    # it. Drop every key_prefix dependency first, then install the exact-HMAC
    # replacement in this same transactional migration.
    op.execute("DROP POLICY IF EXISTS org_isolation ON api_keys;")
    op.execute("DROP POLICY IF EXISTS org_write_isolation ON api_keys;")
    op.drop_index("ix_api_keys_prefix_active", table_name="api_keys")
    op.alter_column(
        "api_keys",
        "key_prefix",
        existing_type=sa.String(length=12),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.execute("UPDATE api_keys SET revoked = true WHERE key_prefix NOT LIKE 'prv_live_%';")
    op.create_check_constraint(
        "ck_api_keys_active_namespaced_prefix",
        "api_keys",
        "revoked OR key_prefix ~ '^prv_live_[A-Za-z0-9_-]{11}\\.\\.\\.$'",
    )
    op.create_index(
        "ix_api_keys_hash_active",
        "api_keys",
        ["key_hash", "revoked"],
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY api_key_select_isolation ON api_keys
            FOR SELECT
            USING (
                org_id = {ORG_CONTEXT_UUID_EXPR}
                OR (
                    current_setting('app.api_key_hash', true) ~ '^[0-9a-f]{{64}}$'
                    AND key_hash = current_setting('app.api_key_hash', true)
                )
            );
        """
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY api_key_write_isolation ON api_keys
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )

    op.create_check_constraint(
        "ck_analysis_credit_ledger_kind",
        "analysis_credit_ledger",
        "kind IN ('purchase', 'consume', 'refund')",
    )
    op.create_check_constraint(
        "ck_analysis_credit_ledger_delta_sign",
        "analysis_credit_ledger",
        "((kind IN ('purchase', 'refund') AND credits_delta > 0) OR "
        "(kind = 'consume' AND credits_delta < 0))",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_credit_ledger_consume_reservation
            ON analysis_credit_ledger (org_id, ((details ->> 'reservation_id')))
            WHERE kind = 'consume' AND details ? 'reservation_id';
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_credit_ledger_refund_reservation
            ON analysis_credit_ledger (org_id, ((details ->> 'reservation_id')))
            WHERE kind = 'refund' AND details ? 'reservation_id';
        """
    )

    op.execute("DROP POLICY IF EXISTS org_isolation ON analysis_credit_ledger;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY credit_ledger_select_isolation ON analysis_credit_ledger
            FOR SELECT
            USING (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY credit_ledger_insert_isolation ON analysis_credit_ledger
            FOR INSERT
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.prevent_analysis_credit_ledger_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            RAISE EXCEPTION 'analysis_credit_ledger is append-only'
                USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_analysis_credit_ledger_append_only
            BEFORE UPDATE OR DELETE ON analysis_credit_ledger
            FOR EACH ROW EXECUTE FUNCTION public.prevent_analysis_credit_ledger_mutation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.validate_analysis_credit_ledger_org()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF NEW.analysis_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.analyses
                WHERE id = NEW.analysis_id AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION 'credit ledger analysis belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.user_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.users
                WHERE id = NEW.user_id AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION 'credit ledger user belongs to another organization'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_analysis_credit_ledger_org_guard
            BEFORE INSERT ON analysis_credit_ledger
            FOR EACH ROW EXECUTE FUNCTION public.validate_analysis_credit_ledger_org();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_analysis_credit_ledger_org_guard ON analysis_credit_ledger;"
    )
    op.execute("DROP FUNCTION IF EXISTS public.validate_analysis_credit_ledger_org();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_analysis_credit_ledger_append_only ON analysis_credit_ledger;"
    )
    op.execute("DROP FUNCTION IF EXISTS public.prevent_analysis_credit_ledger_mutation();")
    op.execute("DROP POLICY IF EXISTS credit_ledger_insert_isolation ON analysis_credit_ledger;")
    op.execute("DROP POLICY IF EXISTS credit_ledger_select_isolation ON analysis_credit_ledger;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON analysis_credit_ledger
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_credit_ledger_refund_reservation;")
    op.execute("DROP INDEX IF EXISTS uq_credit_ledger_consume_reservation;")
    op.drop_constraint(
        "ck_analysis_credit_ledger_delta_sign",
        "analysis_credit_ledger",
        type_="check",
    )
    op.drop_constraint(
        "ck_analysis_credit_ledger_kind",
        "analysis_credit_ledger",
        type_="check",
    )

    # Reverse the dependency-safe upgrade order: remove exact-hash policies and
    # indexes before narrowing key_prefix, then recreate the legacy policies.
    op.execute("DROP POLICY IF EXISTS api_key_write_isolation ON api_keys;")
    op.execute("DROP POLICY IF EXISTS api_key_select_isolation ON api_keys;")
    op.drop_index("ix_api_keys_hash_active", table_name="api_keys")
    op.drop_constraint(
        "ck_api_keys_active_namespaced_prefix",
        "api_keys",
        type_="check",
    )
    op.execute("UPDATE api_keys SET revoked = true, key_prefix = left(key_prefix, 9) || '...';")
    op.alter_column(
        "api_keys",
        "key_prefix",
        existing_type=sa.String(length=32),
        type_=sa.String(length=12),
        existing_nullable=False,
    )
    op.create_index(
        "ix_api_keys_prefix_active",
        "api_keys",
        ["key_prefix", "revoked"],
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON api_keys
            FOR SELECT
            USING (
                org_id = {ORG_CONTEXT_UUID_EXPR}
                OR (
                    current_setting('app.api_key_prefix', true) <> ''
                    AND key_prefix = current_setting('app.api_key_prefix', true)
                )
            );
        """
    )
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_write_isolation ON api_keys
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )

"""Add durable, org-scoped claimed-use counsel receipts.

Revision ID: r4s5t6u7v8w9
Revises: q3r4s5t6u7v8
Create Date: 2026-07-26 22:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "r4s5t6u7v8w9"
down_revision: str | Sequence[str] | None = "q3r4s5t6u7v8"
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
        "analysis_claimed_use_receipts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("report_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("patent_id", sa.String(length=64), nullable=False),
        sa.Column("claim_number", sa.Integer(), nullable=False),
        sa.Column("accused_act_index", sa.Integer(), nullable=False),
        sa.Column("accused_act_sha256", sa.String(length=64), nullable=False),
        sa.Column("receipt_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "receipt_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "issuer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revocation_reason", sa.Text(), server_default="", nullable=False),
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
            "claim_number >= 1 AND accused_act_index >= 0",
            name="ck_analysis_claimed_use_receipts_positive_coordinates",
        ),
        sa.CheckConstraint(
            "report_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND accused_act_sha256 ~ '^[0-9a-f]{64}$' "
            "AND receipt_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_claimed_use_receipts_digests",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_by_user_id IS NULL "
            "AND revocation_reason = '') OR "
            "(revoked_at IS NOT NULL AND revoked_by_user_id IS NOT NULL "
            "AND length(btrim(revocation_reason)) >= 10)",
            name="ck_analysis_claimed_use_receipts_revocation",
        ),
    )
    op.create_index(
        "ix_analysis_claimed_use_receipts_org_analysis",
        "analysis_claimed_use_receipts",
        ["org_id", "analysis_id", "created_at"],
    )
    op.create_index(
        "uq_analysis_claimed_use_receipts_active_subject",
        "analysis_claimed_use_receipts",
        [
            "analysis_id",
            "report_fingerprint",
            "patent_id",
            "claim_number",
            "accused_act_sha256",
        ],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_analysis_claimed_use_receipts_digest",
        "analysis_claimed_use_receipts",
        ["receipt_sha256"],
        unique=True,
    )
    op.create_table(
        "claimed_use_erasure_authorizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("actor_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("transaction_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_kind IN ('platform_superadmin', 'scheduled_system')",
            name="ck_claimed_use_erasure_authorizations_actor_kind",
        ),
        sa.CheckConstraint(
            "(actor_kind = 'platform_superadmin' AND actor_user_id IS NOT NULL) OR "
            "(actor_kind = 'scheduled_system' AND actor_user_id IS NULL)",
            name="ck_claimed_use_erasure_authorizations_actor_binding",
        ),
        sa.CheckConstraint(
            "receipt_count >= 0",
            name="ck_claimed_use_erasure_authorizations_receipt_count",
        ),
    )
    op.create_index(
        "ix_claimed_use_erasure_authorizations_org_created",
        "claimed_use_erasure_authorizations",
        ["org_id", "created_at"],
    )

    # Enforce the tenant, current-report, exact-use, and current-reviewer
    # boundaries beneath the application layer as a final fail-closed guard.
    op.execute(
        """
        CREATE FUNCTION public.validate_claimed_use_receipt_scope()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            accused_act jsonb;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF NOT EXISTS (
                       SELECT 1
                         FROM public.claimed_use_erasure_authorizations AS authorization
                        WHERE authorization.org_id = OLD.org_id
                          AND authorization.created_at = transaction_timestamp()
                          AND authorization.authorized_at
                              BETWEEN statement_timestamp() - interval '5 minutes'
                                  AND statement_timestamp() + interval '30 seconds'
                   ) THEN
                    RAISE EXCEPTION
                        'claimed-use receipt deletion requires explicit tenant erasure authorization'
                        USING ERRCODE = '42501';
                END IF;
                RETURN OLD;
            END IF;

            IF TG_OP = 'UPDATE' AND (
                NEW.id,
                NEW.analysis_id,
                NEW.org_id,
                NEW.report_id,
                NEW.report_fingerprint,
                NEW.patent_id,
                NEW.claim_number,
                NEW.accused_act_index,
                NEW.accused_act_sha256,
                NEW.receipt_sha256,
                NEW.receipt_payload,
                NEW.issuer_user_id,
                NEW.issued_at,
                NEW.created_at
            ) IS DISTINCT FROM (
                OLD.id,
                OLD.analysis_id,
                OLD.org_id,
                OLD.report_id,
                OLD.report_fingerprint,
                OLD.patent_id,
                OLD.claim_number,
                OLD.accused_act_index,
                OLD.accused_act_sha256,
                OLD.receipt_sha256,
                OLD.receipt_payload,
                OLD.issuer_user_id,
                OLD.issued_at,
                OLD.created_at
            ) THEN
                RAISE EXCEPTION 'claimed-use receipt subject and issuer are immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.revoked_at IS NOT NULL AND (
                NEW.revoked_at,
                NEW.revoked_by_user_id,
                NEW.revocation_reason
            ) IS DISTINCT FROM (
                OLD.revoked_at,
                OLD.revoked_by_user_id,
                OLD.revocation_reason
            ) THEN
                RAISE EXCEPTION 'claimed-use receipt revocation is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE'
               AND OLD.revoked_at IS NULL
               AND NEW.revoked_at IS NULL THEN
                RAISE EXCEPTION
                    'claimed-use receipt updates are limited to revocation'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'INSERT' AND NEW.revoked_at IS NOT NULL THEN
                RAISE EXCEPTION
                    'claimed-use receipts cannot be inserted as revoked'
                    USING ERRCODE = '23514';
            END IF;

            IF jsonb_typeof(NEW.receipt_payload) IS DISTINCT FROM 'object'
               OR jsonb_object_length(NEW.receipt_payload) <> 27
               OR NOT (
                   NEW.receipt_payload ?& ARRAY[
                       'schema_version',
                       'analysis_id',
                       'org_id',
                       'report_id',
                       'report_fingerprint',
                       'accused_act_index',
                       'accused_act_sha256',
                       'patent_id',
                       'claim_number',
                       'controlling_claim_text_sha256',
                       'current_claim_receipt_sha256',
                       'controlling_claim_document_ids',
                       'declared_target_product_sha256',
                       'resolved_compound_identity_sha256',
                       'proposed_indication_sha256',
                       'proposed_label_use_sha256',
                       'label_carve_out_state',
                       'claimed_use_match',
                       'product_identity_match',
                       'issuer_user_id',
                       'reviewer_role',
                       'attestation_statement_version',
                       'verified_at',
                       'evidence_references',
                       'attestation_key_id',
                       'attestation_hmac_sha256',
                       'receipt_sha256'
                   ]::text[]
               ) THEN
                RAISE EXCEPTION
                    'claimed-use signed receipt must be an object with every signed field'
                    USING ERRCODE = '23514';
            END IF;

            IF jsonb_typeof(
                   NEW.receipt_payload -> 'controlling_claim_document_ids'
               ) IS DISTINCT FROM 'array'
               OR jsonb_typeof(
                   NEW.receipt_payload -> 'evidence_references'
               ) IS DISTINCT FROM 'array' THEN
                RAISE EXCEPTION
                    'claimed-use signed receipt evidence fields must be arrays'
                    USING ERRCODE = '23514';
            END IF;
            IF jsonb_array_length(
                   NEW.receipt_payload -> 'controlling_claim_document_ids'
               ) NOT BETWEEN 1 AND 20
               OR jsonb_array_length(
                   NEW.receipt_payload -> 'evidence_references'
               ) NOT BETWEEN 1 AND 50 THEN
                RAISE EXCEPTION
                    'claimed-use signed receipt evidence arrays are outside permitted bounds'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.receipt_payload ->> 'schema_version'
                    IS DISTINCT FROM 'claimed-use-match-v3'
               OR NEW.receipt_payload ->> 'receipt_sha256'
                    IS DISTINCT FROM NEW.receipt_sha256
               OR (NEW.receipt_payload ->> 'analysis_id')::uuid
                    IS DISTINCT FROM NEW.analysis_id
               OR (NEW.receipt_payload ->> 'org_id')::uuid
                    IS DISTINCT FROM NEW.org_id
               OR NEW.receipt_payload ->> 'report_id'
                    IS DISTINCT FROM NEW.report_id
               OR NEW.receipt_payload ->> 'report_fingerprint'
                    IS DISTINCT FROM NEW.report_fingerprint
               OR NEW.receipt_payload ->> 'patent_id'
                    IS DISTINCT FROM NEW.patent_id
               OR (NEW.receipt_payload ->> 'claim_number')::integer
                    IS DISTINCT FROM NEW.claim_number
               OR (NEW.receipt_payload ->> 'accused_act_index')::integer
                    IS DISTINCT FROM NEW.accused_act_index
               OR NEW.receipt_payload ->> 'accused_act_sha256'
                    IS DISTINCT FROM NEW.accused_act_sha256
               OR (NEW.receipt_payload ->> 'issuer_user_id')::uuid
                    IS DISTINCT FROM NEW.issuer_user_id
               OR (
                   NEW.receipt_payload ->> 'verified_at'
               ) ~ '(Z|[+-][0-9]{2}:[0-9]{2})$' IS NOT TRUE
               OR (NEW.receipt_payload ->> 'verified_at')::timestamptz
                    IS DISTINCT FROM NEW.issued_at
               OR NEW.receipt_payload -> 'claimed_use_match'
                    IS DISTINCT FROM 'true'::jsonb
               OR NEW.receipt_payload -> 'product_identity_match'
                    IS DISTINCT FROM 'true'::jsonb
               OR NEW.receipt_payload ->> 'reviewer_role'
                    IS DISTINCT FROM 'attorney'
               OR NEW.receipt_payload ->> 'attestation_statement_version'
                    IS DISTINCT FROM 'claimed-use-counsel-affirmation-v1'
               OR (
                   NEW.receipt_payload ->> 'label_carve_out_state'
               ) IN ('none', 'partial', 'complete', 'unknown') IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'controlling_claim_text_sha256'
               ) ~ '^[0-9a-f]{64}$' IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'current_claim_receipt_sha256'
               ) ~ '^[0-9a-f]{64}$' IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'declared_target_product_sha256'
               ) ~ '^[0-9a-f]{64}$' IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'resolved_compound_identity_sha256'
               ) ~ '^[0-9a-f]{64}$' IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'proposed_indication_sha256'
               ) ~ '^[0-9a-f]{64}$' IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'proposed_label_use_sha256'
               ) ~ '^[0-9a-f]{64}$' IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'attestation_key_id'
               ) ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' IS NOT TRUE
               OR (
                   NEW.receipt_payload ->> 'attestation_hmac_sha256'
               ) ~ '^[0-9a-f]{64}$' IS NOT TRUE THEN
                RAISE EXCEPTION
                    'claimed-use persisted coordinates do not match the signed receipt'
                    USING ERRCODE = '23514';
            END IF;

            IF TG_OP = 'INSERT' THEN
                SELECT analysis.config #> ARRAY[
                           'product_context',
                           'accused_acts',
                           NEW.accused_act_index::text
                       ]
                  INTO accused_act
                  FROM public.analyses AS analysis
                 WHERE analysis.id = NEW.analysis_id
                   AND analysis.org_id = NEW.org_id
                   AND analysis.status::text = 'completed'
                   AND analysis.report_data ->> 'report_id' = NEW.report_id
                   AND analysis.report_data -> 'patent_details' ? NEW.patent_id;
                IF accused_act IS NULL
                   OR accused_act ->> 'act' <> 'regulatory_submission' THEN
                    RAISE EXCEPTION
                        'claimed-use receipt is outside the current report or proposed-use scope'
                        USING ERRCODE = '23514';
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                      FROM public.users AS issuer
                     WHERE issuer.id = NEW.issuer_user_id
                       AND issuer.org_id = NEW.org_id
                       AND issuer.role::text = 'attorney'
                       AND issuer.membership_active = true
                       AND issuer.membership_deleted_at IS NULL
                       AND issuer.membership_permission_denied_at IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'claimed-use receipt issuer lacks current authority'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            IF NEW.revoked_by_user_id IS NOT NULL AND NOT EXISTS (
                SELECT 1
                  FROM public.users AS revoker
                 WHERE revoker.id = NEW.revoked_by_user_id
                   AND revoker.org_id = NEW.org_id
                   AND (
                       revoker.role::text = 'admin'
                       OR (
                           revoker.role::text = 'attorney'
                           AND revoker.id = NEW.issuer_user_id
                       )
                   )
                   AND revoker.membership_active = true
                   AND revoker.membership_deleted_at IS NULL
                   AND revoker.membership_permission_denied_at IS NULL
            ) THEN
                RAISE EXCEPTION 'claimed-use receipt revoker lacks current authority'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_claimed_use_receipt_scope_guard
            BEFORE INSERT OR UPDATE OR DELETE
            ON analysis_claimed_use_receipts
            FOR EACH ROW
            EXECUTE FUNCTION public.validate_claimed_use_receipt_scope();
        """
    )
    op.execute("ALTER TABLE analysis_claimed_use_receipts ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE analysis_claimed_use_receipts FORCE ROW LEVEL SECURITY;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON analysis_claimed_use_receipts
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.execute("ALTER TABLE claimed_use_erasure_authorizations ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE claimed_use_erasure_authorizations FORCE ROW LEVEL SECURITY;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON claimed_use_erasure_authorizations
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.reject_claimed_use_erasure_authorization_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            RAISE EXCEPTION
                'claimed-use erasure authorizations are append-only'
                USING ERRCODE = '42501';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_claimed_use_erasure_authorization_append_only
            BEFORE UPDATE OR DELETE
            ON claimed_use_erasure_authorizations
            FOR EACH ROW
            EXECUTE FUNCTION public.reject_claimed_use_erasure_authorization_mutation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.issue_claimed_use_receipt(
            p_receipt_payload jsonb
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            receipt_id uuid := gen_random_uuid();
            receipt_org_id uuid;
        BEGIN
            receipt_org_id := (p_receipt_payload ->> 'org_id')::uuid;
            PERFORM set_config('app.current_org_id', receipt_org_id::text, true);

            INSERT INTO public.analysis_claimed_use_receipts (
                id,
                analysis_id,
                org_id,
                report_id,
                report_fingerprint,
                patent_id,
                claim_number,
                accused_act_index,
                accused_act_sha256,
                receipt_sha256,
                receipt_payload,
                issuer_user_id,
                issued_at
            ) VALUES (
                receipt_id,
                (p_receipt_payload ->> 'analysis_id')::uuid,
                receipt_org_id,
                p_receipt_payload ->> 'report_id',
                p_receipt_payload ->> 'report_fingerprint',
                p_receipt_payload ->> 'patent_id',
                (p_receipt_payload ->> 'claim_number')::integer,
                (p_receipt_payload ->> 'accused_act_index')::integer,
                p_receipt_payload ->> 'accused_act_sha256',
                p_receipt_payload ->> 'receipt_sha256',
                p_receipt_payload,
                (p_receipt_payload ->> 'issuer_user_id')::uuid,
                (p_receipt_payload ->> 'verified_at')::timestamptz
            );
            RETURN receipt_id;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.revoke_claimed_use_receipt(
            p_receipt_id uuid,
            p_org_id uuid,
            p_revoked_by_user_id uuid,
            p_revocation_reason text,
            p_revoked_at timestamptz
        )
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            PERFORM set_config('app.current_org_id', p_org_id::text, true);
            UPDATE public.analysis_claimed_use_receipts
               SET revoked_at = p_revoked_at,
                   revoked_by_user_id = p_revoked_by_user_id,
                   revocation_reason = p_revocation_reason,
                   updated_at = statement_timestamp()
             WHERE id = p_receipt_id
               AND org_id = p_org_id
               AND revoked_at IS NULL;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'claimed-use receipt was not found or already revoked'
                    USING ERRCODE = 'P0002';
            END IF;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.erase_claimed_use_receipts(
            p_authorization_id uuid,
            p_request_id uuid,
            p_org_id uuid,
            p_actor_kind text,
            p_actor_user_id uuid,
            p_authorized_at timestamptz
        )
        RETURNS bigint
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            expected_count bigint;
            erased_count bigint;
        BEGIN
            IF p_authorized_at NOT BETWEEN statement_timestamp() - interval '5 minutes'
                                       AND statement_timestamp() + interval '30 seconds' THEN
                RAISE EXCEPTION 'erasure authorization is outside the permitted time window'
                    USING ERRCODE = '42501';
            END IF;
            IF p_actor_kind = 'platform_superadmin' THEN
                IF p_actor_user_id IS NULL OR NOT EXISTS (
                    SELECT 1
                      FROM public.users
                     WHERE id = p_actor_user_id
                       AND role::text = 'admin'
                       AND membership_active = true
                       AND membership_deleted_at IS NULL
                       AND membership_permission_denied_at IS NULL
                ) THEN
                    RAISE EXCEPTION 'platform erasure actor lacks current authority'
                        USING ERRCODE = '42501';
                END IF;
            ELSIF p_actor_kind = 'scheduled_system' THEN
                IF p_actor_user_id IS NOT NULL OR NOT EXISTS (
                    SELECT 1
                      FROM public.organizations
                     WHERE id = p_org_id
                       AND deletion_status IN (
                           'pending',
                           'billing_cancellation_pending',
                           'archive_deletion_pending'
                       )
                       AND deletion_scheduled_at IS NOT NULL
                       AND deletion_scheduled_at <= statement_timestamp()
                ) THEN
                    RAISE EXCEPTION 'scheduled erasure is not due'
                        USING ERRCODE = '42501';
                END IF;
            ELSE
                RAISE EXCEPTION 'unknown erasure actor kind'
                    USING ERRCODE = '42501';
            END IF;

            PERFORM set_config('app.current_org_id', p_org_id::text, true);
            SELECT count(*)
              INTO expected_count
              FROM public.analysis_claimed_use_receipts
             WHERE org_id = p_org_id;

            INSERT INTO public.claimed_use_erasure_authorizations (
                id,
                request_id,
                org_id,
                actor_kind,
                actor_user_id,
                authorized_at,
                receipt_count
            ) VALUES (
                p_authorization_id,
                p_request_id,
                p_org_id,
                p_actor_kind,
                p_actor_user_id,
                p_authorized_at,
                expected_count
            );

            DELETE FROM public.analysis_claimed_use_receipts
             WHERE org_id = p_org_id;
            GET DIAGNOSTICS erased_count = ROW_COUNT;
            IF erased_count <> expected_count THEN
                RAISE EXCEPTION 'claimed-use erasure count changed during execution'
                    USING ERRCODE = '40001';
            END IF;
            RETURN erased_count;
        END;
        $$;
        """
    )
    op.execute(
        """
        REVOKE ALL ON FUNCTION public.issue_claimed_use_receipt(jsonb) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.revoke_claimed_use_receipt(
            uuid, uuid, uuid, text, timestamptz
        ) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.erase_claimed_use_receipts(
            uuid, uuid, uuid, text, uuid, timestamptz
        ) FROM PUBLIC;
        REVOKE ALL ON claimed_use_erasure_authorizations FROM PUBLIC;
        DO $$
        DECLARE role_name text;
        BEGIN
            FOREACH role_name IN ARRAY ARRAY['praviar_api', 'praviar_worker']
            LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                    EXECUTE format(
                        'REVOKE INSERT, UPDATE, DELETE ON public.analysis_claimed_use_receipts FROM %I',
                        role_name
                    );
                    EXECUTE format(
                        'REVOKE ALL ON public.claimed_use_erasure_authorizations FROM %I',
                        role_name
                    );
                    EXECUTE format(
                        'REVOKE UPDATE, DELETE ON public.audit_logs FROM %I',
                        role_name
                    );
                    EXECUTE format(
                        'REVOKE ALL ON FUNCTION public.issue_claimed_use_receipt(jsonb) FROM %I',
                        role_name
                    );
                    EXECUTE format(
                        'REVOKE ALL ON FUNCTION public.revoke_claimed_use_receipt(uuid, uuid, uuid, text, timestamptz) FROM %I',
                        role_name
                    );
                    EXECUTE format(
                        'REVOKE ALL ON FUNCTION public.erase_claimed_use_receipts(uuid, uuid, uuid, text, uuid, timestamptz) FROM %I',
                        role_name
                    );
                END IF;
            END LOOP;
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'praviar_claimed_use_writer'
            ) THEN
                GRANT SELECT ON public.analysis_claimed_use_receipts
                    TO praviar_claimed_use_writer;
                GRANT EXECUTE ON FUNCTION public.issue_claimed_use_receipt(jsonb)
                    TO praviar_claimed_use_writer;
                GRANT EXECUTE ON FUNCTION public.revoke_claimed_use_receipt(
                    uuid, uuid, uuid, text, timestamptz
                ) TO praviar_claimed_use_writer;
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'praviar_global_erasure'
            ) THEN
                GRANT EXECUTE ON FUNCTION public.erase_claimed_use_receipts(
                    uuid, uuid, uuid, text, uuid, timestamptz
                ) TO praviar_global_erasure;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE analysis_claimed_use_receipts NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE claimed_use_erasure_authorizations NO FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM analysis_claimed_use_receipts)
               OR EXISTS (SELECT 1 FROM claimed_use_erasure_authorizations) THEN
                EXECUTE
                    'ALTER TABLE analysis_claimed_use_receipts FORCE ROW LEVEL SECURITY';
                EXECUTE
                    'ALTER TABLE claimed_use_erasure_authorizations FORCE ROW LEVEL SECURITY';
                RAISE EXCEPTION
                    'Refusing to downgrade while claimed-use legal-ledger records remain';
            END IF;
        EXCEPTION WHEN OTHERS THEN
            EXECUTE
                'ALTER TABLE analysis_claimed_use_receipts FORCE ROW LEVEL SECURITY';
            EXECUTE
                'ALTER TABLE claimed_use_erasure_authorizations FORCE ROW LEVEL SECURITY';
            RAISE;
        END
        $$;
        """
    )
    op.execute("DROP POLICY IF EXISTS org_isolation ON analysis_claimed_use_receipts;")
    op.execute("DROP POLICY IF EXISTS org_isolation ON claimed_use_erasure_authorizations;")
    op.execute(
        "DROP FUNCTION IF EXISTS public.erase_claimed_use_receipts("
        "uuid, uuid, uuid, text, uuid, timestamptz);"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.revoke_claimed_use_receipt("
        "uuid, uuid, uuid, text, timestamptz);"
    )
    op.execute("DROP FUNCTION IF EXISTS public.issue_claimed_use_receipt(jsonb);")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_claimed_use_erasure_authorization_append_only "
        "ON claimed_use_erasure_authorizations;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.reject_claimed_use_erasure_authorization_mutation();"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_claimed_use_receipt_scope_guard "
        "ON analysis_claimed_use_receipts;"
    )
    op.execute("DROP FUNCTION IF EXISTS public.validate_claimed_use_receipt_scope();")
    op.drop_table("claimed_use_erasure_authorizations")
    op.drop_table("analysis_claimed_use_receipts")

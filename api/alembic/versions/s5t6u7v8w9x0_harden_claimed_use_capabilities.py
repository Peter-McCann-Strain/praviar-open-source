"""Harden claimed-use erasure around independently issued capabilities.

Revision ID: s5t6u7v8w9x0
Revises: r4s5t6u7v8w9
Create Date: 2026-07-27 13:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "s5t6u7v8w9x0"
down_revision: str | Sequence[str] | None = "r4s5t6u7v8w9"
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
        "claimed_use_erasure_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability_sha256", sa.String(length=64), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("transaction_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_kind IN ('platform_superadmin', 'scheduled_system')",
            name="ck_claimed_use_erasure_capabilities_actor_kind",
        ),
        sa.CheckConstraint(
            "(actor_kind = 'platform_superadmin' AND actor_user_id IS NOT NULL) OR "
            "(actor_kind = 'scheduled_system' AND actor_user_id IS NULL)",
            name="ck_claimed_use_erasure_capabilities_actor_binding",
        ),
        sa.CheckConstraint(
            "capability_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_claimed_use_erasure_capabilities_digest",
        ),
        sa.CheckConstraint(
            "expires_at > authorized_at AND expires_at <= authorized_at + interval '5 minutes'",
            name="ck_claimed_use_erasure_capabilities_expiry",
        ),
    )
    op.create_index(
        "ix_claimed_use_erasure_capabilities_org_created",
        "claimed_use_erasure_capabilities",
        ["org_id", "created_at"],
    )
    op.execute("ALTER TABLE claimed_use_erasure_capabilities ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE claimed_use_erasure_capabilities FORCE ROW LEVEL SECURITY;")
    op.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        f"""
        CREATE POLICY org_isolation ON claimed_use_erasure_capabilities
            FOR ALL
            USING (org_id = {ORG_CONTEXT_UUID_EXPR})
            WITH CHECK (org_id = {ORG_CONTEXT_UUID_EXPR});
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_claimed_use_erasure_capability_append_only
            BEFORE UPDATE OR DELETE
            ON claimed_use_erasure_capabilities
            FOR EACH ROW
            EXECUTE FUNCTION
                public.reject_claimed_use_erasure_authorization_mutation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.authorize_claimed_use_erasure(
            p_authorization_id uuid,
            p_request_id uuid,
            p_org_id uuid,
            p_actor_kind text,
            p_actor_user_id uuid,
            p_capability_sha256 text
        )
        RETURNS timestamptz
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            issued_at timestamptz := statement_timestamp();
        BEGIN
            IF p_capability_sha256 !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'invalid erasure capability digest'
                    USING ERRCODE = '22023';
            END IF;

            IF p_actor_kind = 'platform_superadmin' THEN
                IF session_user <> 'praviar_api'
                   OR p_actor_user_id IS NULL
                   OR NOT EXISTS (
                        SELECT 1
                          FROM public.users
                         WHERE id = p_actor_user_id
                           AND role::text = 'admin'
                           AND membership_active = true
                           AND membership_deleted_at IS NULL
                           AND membership_permission_denied_at IS NULL
                   ) THEN
                    RAISE EXCEPTION
                        'platform erasure capability lacks authenticated authority'
                        USING ERRCODE = '42501';
                END IF;
            ELSIF p_actor_kind = 'scheduled_system' THEN
                IF session_user <> 'praviar_worker'
                   OR p_actor_user_id IS NOT NULL
                   OR NOT EXISTS (
                        SELECT 1
                          FROM public.organizations
                         WHERE id = p_org_id
                           AND deletion_status IN (
                               'pending',
                               'billing_cancellation_pending',
                               'archive_deletion_pending'
                           )
                           AND deletion_scheduled_at IS NOT NULL
                           AND deletion_scheduled_at <= issued_at
                   ) THEN
                    RAISE EXCEPTION
                        'scheduled erasure capability is not due'
                        USING ERRCODE = '42501';
                END IF;
            ELSE
                RAISE EXCEPTION 'unknown erasure capability actor kind'
                    USING ERRCODE = '42501';
            END IF;

            PERFORM set_config('app.current_org_id', p_org_id::text, true);
            INSERT INTO public.claimed_use_erasure_capabilities (
                id,
                request_id,
                org_id,
                actor_kind,
                actor_user_id,
                capability_sha256,
                authorized_at,
                expires_at
            ) VALUES (
                p_authorization_id,
                p_request_id,
                p_org_id,
                p_actor_kind,
                p_actor_user_id,
                p_capability_sha256,
                issued_at,
                issued_at + interval '5 minutes'
            );
            RETURN issued_at;
        END;
        $$;
        """
    )
    op.execute(
        """
        REVOKE ALL ON FUNCTION public.erase_claimed_use_receipts(
            uuid, uuid, uuid, text, uuid, timestamptz
        ) FROM PUBLIC;
        DROP FUNCTION public.erase_claimed_use_receipts(
            uuid, uuid, uuid, text, uuid, timestamptz
        );
        CREATE FUNCTION public.erase_claimed_use_receipts(
            p_authorization_id uuid,
            p_request_id uuid,
            p_org_id uuid,
            p_actor_user_id uuid,
            p_capability_secret text
        )
        RETURNS bigint
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            capability public.claimed_use_erasure_capabilities%ROWTYPE;
            expected_count bigint;
            erased_count bigint;
        BEGIN
            IF p_capability_secret IS NULL
               OR length(p_capability_secret) < 32 THEN
                RAISE EXCEPTION 'invalid erasure capability'
                    USING ERRCODE = '42501';
            END IF;

            PERFORM set_config('app.current_org_id', p_org_id::text, true);
            SELECT *
              INTO capability
              FROM public.claimed_use_erasure_capabilities
             WHERE id = p_authorization_id
               AND request_id = p_request_id
               AND org_id = p_org_id
               AND actor_user_id IS NOT DISTINCT FROM p_actor_user_id
             FOR SHARE;
            IF NOT FOUND
               OR capability.expires_at < statement_timestamp()
               OR capability.capability_sha256
                    <> encode(
                        sha256(convert_to(p_capability_secret, 'UTF8')),
                        'hex'
                    )
               OR EXISTS (
                    SELECT 1
                      FROM public.claimed_use_erasure_authorizations
                     WHERE id = p_authorization_id
                        OR request_id = p_request_id
               ) THEN
                RAISE EXCEPTION
                    'erasure capability is invalid, expired, or already consumed'
                    USING ERRCODE = '42501';
            END IF;

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
                capability.id,
                capability.request_id,
                capability.org_id,
                capability.actor_kind,
                capability.actor_user_id,
                capability.authorized_at,
                expected_count
            );

            DELETE FROM public.analysis_claimed_use_receipts
             WHERE org_id = p_org_id;
            GET DIAGNOSTICS erased_count = ROW_COUNT;
            IF erased_count <> expected_count THEN
                RAISE EXCEPTION
                    'claimed-use erasure count changed during execution'
                    USING ERRCODE = '40001';
            END IF;
            RETURN erased_count;
        END;
        $$;
        """
    )
    op.execute(
        """
        REVOKE ALL ON claimed_use_erasure_capabilities FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.authorize_claimed_use_erasure(
            uuid, uuid, uuid, text, uuid, text
        ) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.erase_claimed_use_receipts(
            uuid, uuid, uuid, uuid, text
        ) FROM PUBLIC;
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'praviar_api'
            ) THEN
                GRANT EXECUTE ON FUNCTION public.authorize_claimed_use_erasure(
                    uuid, uuid, uuid, text, uuid, text
                ) TO praviar_api;
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'praviar_worker'
            ) THEN
                GRANT EXECUTE ON FUNCTION public.authorize_claimed_use_erasure(
                    uuid, uuid, uuid, text, uuid, text
                ) TO praviar_worker;
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'praviar_global_erasure'
            ) THEN
                GRANT EXECUTE ON FUNCTION public.erase_claimed_use_receipts(
                    uuid, uuid, uuid, uuid, text
                ) TO praviar_global_erasure;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM claimed_use_erasure_capabilities
            ) THEN
                RAISE EXCEPTION
                    'Refusing to downgrade while claimed-use erasure capabilities remain';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DROP FUNCTION public.erase_claimed_use_receipts(
            uuid, uuid, uuid, uuid, text
        );
        DROP FUNCTION public.authorize_claimed_use_erasure(
            uuid, uuid, uuid, text, uuid, text
        );
        DROP TABLE claimed_use_erasure_capabilities;

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

        REVOKE ALL ON FUNCTION public.erase_claimed_use_receipts(
            uuid, uuid, uuid, text, uuid, timestamptz
        ) FROM PUBLIC;
        DO $$
        BEGIN
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

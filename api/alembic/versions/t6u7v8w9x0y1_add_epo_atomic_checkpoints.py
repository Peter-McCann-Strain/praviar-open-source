"""Add durable, two-row EPO provenance checkpoints.

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-07-27 15:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "t6u7v8w9x0y1"
down_revision: str | Sequence[str] | None = "s5t6u7v8w9x0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _checkpoint_columns() -> list[sa.Column]:
    return [
        sa.Column("source_stream_id", sa.String(length=128), nullable=False),
        sa.Column("schema_epoch", sa.Integer(), nullable=False),
        sa.Column("manifest_type", sa.String(length=16), nullable=False),
        sa.Column("canonical_subject", sa.String(length=9), nullable=False),
        sa.Column("required_as_of", sa.Date(), nullable=False),
        sa.Column("checkpoint_generation", sa.BigInteger(), nullable=False),
        sa.Column("checkpoint_envelope_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "prior_checkpoint_envelope_sha256",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column("source_snapshot_sequence", sa.BigInteger(), nullable=False),
        sa.Column("minimum_snapshot_sequence", sa.BigInteger(), nullable=False),
        sa.Column(
            "source_acquisition_envelope_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "counterpart_source_acquisition_envelope_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("checkpoint_batch_sha256", sa.String(length=64), nullable=False),
        sa.Column("signing_key_id", sa.String(length=64), nullable=False),
        sa.Column("key_revocation_epoch", sa.BigInteger(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkpoint_signature", sa.LargeBinary(), nullable=False),
    ]


def _checkpoint_constraints(prefix: str) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            "source_stream_id ~ '^[a-z0-9][a-z0-9._-]{2,127}$'",
            name=f"ck_{prefix}_source_stream",
        ),
        sa.CheckConstraint("schema_epoch >= 1", name=f"ck_{prefix}_schema_epoch"),
        sa.CheckConstraint(
            "manifest_type IN ('authority', 'register')",
            name=f"ck_{prefix}_manifest_type",
        ),
        sa.CheckConstraint(
            "(manifest_type = 'authority' AND canonical_subject ~ '^[0-9]{7}$') OR "
            "(manifest_type = 'register' AND canonical_subject ~ '^EP[0-9]{7}$')",
            name=f"ck_{prefix}_subject",
        ),
        sa.CheckConstraint(
            "checkpoint_generation >= 1 "
            "AND source_snapshot_sequence >= 1 "
            "AND minimum_snapshot_sequence >= 1 "
            "AND source_snapshot_sequence >= minimum_snapshot_sequence "
            "AND key_revocation_epoch >= 0",
            name=f"ck_{prefix}_positive_counters",
        ),
        sa.CheckConstraint(
            "(checkpoint_generation = 1) = "
            "(prior_checkpoint_envelope_sha256 IS NULL)",
            name=f"ck_{prefix}_lineage",
        ),
        sa.CheckConstraint(
            "checkpoint_envelope_sha256 ~ '^[0-9a-f]{64}$' "
            "AND (prior_checkpoint_envelope_sha256 IS NULL OR "
            "prior_checkpoint_envelope_sha256 ~ '^[0-9a-f]{64}$') "
            "AND source_acquisition_envelope_sha256 ~ '^[0-9a-f]{64}$' "
            "AND counterpart_source_acquisition_envelope_sha256 ~ '^[0-9a-f]{64}$' "
            "AND checkpoint_batch_sha256 ~ '^[0-9a-f]{64}$'",
            name=f"ck_{prefix}_digests",
        ),
        sa.CheckConstraint(
            "signing_key_id ~ '^[a-z0-9][a-z0-9._-]{2,63}$' "
            "AND octet_length(checkpoint_signature) = 64",
            name=f"ck_{prefix}_signature",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "epo_atomic_checkpoints",
        *_checkpoint_columns(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("transaction_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("transaction_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "canonical_subject",
            name="pk_epo_atomic_checkpoints",
        ),
        sa.UniqueConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "checkpoint_batch_sha256",
            name="uq_epo_atomic_checkpoints_manifest_batch",
        ),
        *_checkpoint_constraints("epo_atomic_checkpoints"),
    )
    op.create_table(
        "epo_atomic_checkpoint_history",
        *_checkpoint_columns(),
        sa.Column(
            "persisted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("transaction_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "canonical_subject",
            "checkpoint_generation",
            name="pk_epo_atomic_checkpoint_history",
        ),
        sa.UniqueConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "checkpoint_batch_sha256",
            name="uq_epo_atomic_checkpoint_history_manifest_batch",
        ),
        sa.UniqueConstraint(
            "source_stream_id",
            "schema_epoch",
            "manifest_type",
            "canonical_subject",
            "checkpoint_envelope_sha256",
            name="uq_epo_atomic_checkpoint_history_envelope",
        ),
        *_checkpoint_constraints("epo_atomic_checkpoint_history"),
    )

    op.execute(
        """
        CREATE FUNCTION public.guard_epo_atomic_checkpoint_monotonicity()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'EPO current checkpoints cannot be deleted'
                    USING ERRCODE = '42501';
            END IF;
            IF TG_OP = 'UPDATE' AND (
                NEW.source_stream_id,
                NEW.schema_epoch,
                NEW.manifest_type,
                NEW.canonical_subject
            ) IS DISTINCT FROM (
                OLD.source_stream_id,
                OLD.schema_epoch,
                OLD.manifest_type,
                OLD.canonical_subject
            ) THEN
                RAISE EXCEPTION 'EPO checkpoint identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'UPDATE' AND (
                NEW.checkpoint_generation <> OLD.checkpoint_generation + 1
                OR NEW.prior_checkpoint_envelope_sha256
                    IS DISTINCT FROM OLD.checkpoint_envelope_sha256
                OR NEW.source_snapshot_sequence <= OLD.source_snapshot_sequence
                OR NEW.minimum_snapshot_sequence < OLD.minimum_snapshot_sequence
                OR NEW.required_as_of < OLD.required_as_of
            ) THEN
                RAISE EXCEPTION 'EPO checkpoint monotonicity violation'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$;

        CREATE TRIGGER trg_epo_atomic_checkpoint_monotonicity
        BEFORE UPDATE OR DELETE ON public.epo_atomic_checkpoints
        FOR EACH ROW EXECUTE FUNCTION public.guard_epo_atomic_checkpoint_monotonicity();

        CREATE FUNCTION public.guard_epo_atomic_checkpoint_pair()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            counterpart_type text;
            counterpart_subject text;
        BEGIN
            IF NEW.manifest_type = 'authority' THEN
                counterpart_type := 'register';
                counterpart_subject := 'EP' || NEW.canonical_subject;
            ELSE
                counterpart_type := 'authority';
                counterpart_subject := substring(NEW.canonical_subject FROM 3);
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM public.epo_atomic_checkpoints AS counterpart
                WHERE counterpart.source_stream_id = NEW.source_stream_id
                  AND counterpart.schema_epoch = NEW.schema_epoch
                  AND counterpart.manifest_type = counterpart_type
                  AND counterpart.canonical_subject = counterpart_subject
                  AND counterpart.required_as_of = NEW.required_as_of
                  AND counterpart.checkpoint_batch_sha256 = NEW.checkpoint_batch_sha256
                  AND counterpart.source_acquisition_envelope_sha256 =
                      NEW.counterpart_source_acquisition_envelope_sha256
                  AND counterpart.counterpart_source_acquisition_envelope_sha256 =
                      NEW.source_acquisition_envelope_sha256
            ) THEN
                RAISE EXCEPTION 'EPO checkpoint pair is torn or causally mixed'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END
        $$;

        CREATE CONSTRAINT TRIGGER trg_epo_atomic_checkpoint_pair
        AFTER INSERT OR UPDATE ON public.epo_atomic_checkpoints
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION public.guard_epo_atomic_checkpoint_pair();

        CREATE FUNCTION public.guard_epo_atomic_checkpoint_history()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        BEGIN
            RAISE EXCEPTION 'EPO checkpoint history is append-only'
                USING ERRCODE = '42501';
        END
        $$;

        CREATE TRIGGER trg_epo_atomic_checkpoint_history_immutable
        BEFORE UPDATE OR DELETE ON public.epo_atomic_checkpoint_history
        FOR EACH ROW EXECUTE FUNCTION public.guard_epo_atomic_checkpoint_history();

        CREATE FUNCTION public.guard_epo_atomic_checkpoint_history_pair()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $$
        DECLARE
            counterpart_type text;
            counterpart_subject text;
        BEGIN
            IF NEW.manifest_type = 'authority' THEN
                counterpart_type := 'register';
                counterpart_subject := 'EP' || NEW.canonical_subject;
            ELSE
                counterpart_type := 'authority';
                counterpart_subject := substring(NEW.canonical_subject FROM 3);
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM public.epo_atomic_checkpoint_history AS counterpart
                WHERE counterpart.source_stream_id = NEW.source_stream_id
                  AND counterpart.schema_epoch = NEW.schema_epoch
                  AND counterpart.manifest_type = counterpart_type
                  AND counterpart.canonical_subject = counterpart_subject
                  AND counterpart.required_as_of = NEW.required_as_of
                  AND counterpart.checkpoint_batch_sha256 = NEW.checkpoint_batch_sha256
                  AND counterpart.source_acquisition_envelope_sha256 =
                      NEW.counterpart_source_acquisition_envelope_sha256
                  AND counterpart.counterpart_source_acquisition_envelope_sha256 =
                      NEW.source_acquisition_envelope_sha256
            ) THEN
                RAISE EXCEPTION 'EPO checkpoint history pair is torn or causally mixed'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NULL;
        END
        $$;

        CREATE CONSTRAINT TRIGGER trg_epo_atomic_checkpoint_history_pair
        AFTER INSERT ON public.epo_atomic_checkpoint_history
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION public.guard_epo_atomic_checkpoint_history_pair();

        REVOKE ALL ON FUNCTION public.guard_epo_atomic_checkpoint_monotonicity()
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.guard_epo_atomic_checkpoint_pair()
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.guard_epo_atomic_checkpoint_history()
            FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.guard_epo_atomic_checkpoint_history_pair()
            FROM PUBLIC;
        REVOKE ALL ON public.epo_atomic_checkpoints FROM PUBLIC;
        REVOKE ALL ON public.epo_atomic_checkpoint_history FROM PUBLIC;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            runtime_role text;
        BEGIN
            FOREACH runtime_role IN ARRAY ARRAY[
                'praviar_api',
                'praviar_worker',
                'praviar_claimed_use_writer',
                'praviar_global_erasure'
            ]
            LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = runtime_role) THEN
                    EXECUTE format(
                        'REVOKE ALL ON public.epo_atomic_checkpoints FROM %I',
                        runtime_role
                    );
                    EXECUTE format(
                        'REVOKE ALL ON public.epo_atomic_checkpoint_history FROM %I',
                        runtime_role
                    );
                END IF;
            END LOOP;
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'praviar_epo_checkpoint_writer'
            ) THEN
                GRANT SELECT, INSERT, UPDATE ON public.epo_atomic_checkpoints
                    TO praviar_epo_checkpoint_writer;
                GRANT SELECT, INSERT ON public.epo_atomic_checkpoint_history
                    TO praviar_epo_checkpoint_writer;
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
            IF EXISTS (SELECT 1 FROM public.epo_atomic_checkpoints)
               OR EXISTS (SELECT 1 FROM public.epo_atomic_checkpoint_history) THEN
                RAISE EXCEPTION
                    'Refusing to downgrade: EPO checkpoint provenance records exist. '
                    'Export and explicitly authorize their destruction first.';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_epo_atomic_checkpoint_history_pair
            ON public.epo_atomic_checkpoint_history;
        DROP TRIGGER IF EXISTS trg_epo_atomic_checkpoint_history_immutable
            ON public.epo_atomic_checkpoint_history;
        DROP TRIGGER IF EXISTS trg_epo_atomic_checkpoint_pair
            ON public.epo_atomic_checkpoints;
        DROP TRIGGER IF EXISTS trg_epo_atomic_checkpoint_monotonicity
            ON public.epo_atomic_checkpoints;
        DROP FUNCTION IF EXISTS public.guard_epo_atomic_checkpoint_history_pair();
        DROP FUNCTION IF EXISTS public.guard_epo_atomic_checkpoint_history();
        DROP FUNCTION IF EXISTS public.guard_epo_atomic_checkpoint_pair();
        DROP FUNCTION IF EXISTS public.guard_epo_atomic_checkpoint_monotonicity();
        """
    )
    op.drop_table("epo_atomic_checkpoint_history")
    op.drop_table("epo_atomic_checkpoints")

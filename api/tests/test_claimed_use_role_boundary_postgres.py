"""Live PostgreSQL canary for the claimed-use legal-ledger capability boundary."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from praviar_pipeline.models.accused_acts import (
    ClaimedUseMatchReceipt,
    create_claimed_use_match_receipt,
    verify_claimed_use_match_attestation,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from api.db.claimed_use_privileged import (
    dispose_claimed_use_privileged_engines,
    verify_claimed_use_privilege_boundary,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_CLAIMED_USE_BOUNDARY_TESTS") != "1",
    reason="claimed-use capability canary runs in the dedicated PostgreSQL CI job",
)

_ATTESTATION_KEY = b"postgres-claimed-use-canary-key-32b"


def _engine(env_name: str) -> AsyncEngine:
    url = os.environ[env_name]
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail(f"{env_name} must be an asyncpg PostgreSQL URL")
    return create_async_engine(url)


async def _must_fail(engine: AsyncEngine, sql: str, params: dict | None = None) -> None:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            with pytest.raises(SQLAlchemyError):
                await connection.execute(text(sql), params or {})
        finally:
            await transaction.rollback()


async def _role_security_state(engine: AsyncEngine) -> dict[str, object]:
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT
                        runtime_role.rolname AS principal,
                        runtime_role.rolsuper AS is_superuser,
                        runtime_role.rolbypassrls AS bypass_rls,
                        runtime_role.rolinherit AS inherits_privileges,
                        runtime_role.rolcanlogin AS can_login,
                        (
                            SELECT count(*)
                              FROM pg_auth_members AS membership
                             WHERE membership.member = runtime_role.oid
                        ) AS membership_count
                      FROM pg_roles AS runtime_role
                     WHERE runtime_role.rolname = current_user
                    """
                    )
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


async def _assert_protected_function_catalog_contract(
    admin_engine: AsyncEngine,
) -> None:
    async with admin_engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        WITH protected(signature) AS (
                            VALUES
                                ('public.issue_claimed_use_receipt(jsonb)'),
                                (
                                    'public.revoke_claimed_use_receipt('
                                    'uuid,uuid,uuid,text,timestamp with time zone)'
                                ),
                                (
                                    'public.authorize_claimed_use_erasure('
                                    'uuid,uuid,uuid,text,uuid,text)'
                                ),
                                (
                                    'public.erase_claimed_use_receipts('
                                    'uuid,uuid,uuid,uuid,text)'
                                )
                        )
                        SELECT
                            protected.signature,
                            protected_function.oid IS NOT NULL AS function_exists,
                            function_owner.rolname AS owner_name,
                            function_owner.rolcanlogin AS owner_can_login,
                            CASE
                                WHEN protected_function.oid IS NULL THEN NULL
                                ELSE EXISTS (
                                    SELECT 1
                                      FROM aclexplode(
                                        COALESCE(
                                            protected_function.proacl,
                                            acldefault(
                                                'f',
                                                protected_function.proowner
                                            )
                                        )
                                      ) AS privilege
                                     WHERE privilege.grantee = 0
                                       AND privilege.privilege_type = 'EXECUTE'
                                )
                            END AS public_can_execute
                          FROM protected
                          LEFT JOIN pg_proc AS protected_function
                            ON protected_function.oid = to_regprocedure(
                                protected.signature
                            )
                          LEFT JOIN pg_roles AS function_owner
                            ON function_owner.oid = protected_function.proowner
                        """
                    )
                )
            )
            .mappings()
            .all()
        )

    assert len(rows) == 4
    assert all(row["function_exists"] for row in rows)
    assert all(not row["public_can_execute"] for row in rows)
    assert all(not row["owner_can_login"] for row in rows)
    owners = {row["owner_name"] for row in rows}
    assert len(owners) == 1
    assert owners.isdisjoint(
        {
            "praviar_api",
            "praviar_worker",
            "praviar_claimed_use_writer",
            "praviar_global_erasure",
        }
    )


def _receipt_payload(
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    attorney_id: uuid.UUID,
    report_id: str,
    report_fingerprint: str,
    issued_at: datetime,
) -> dict[str, object]:
    compound = SimpleNamespace(
        model_dump=lambda **_kwargs: {
            "compound_type": "small_molecule",
            "name": "aspirin",
            "canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
            "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            "original_input": "aspirin",
        }
    )
    receipt = create_claimed_use_match_receipt(
        analysis_id=analysis_id,
        org_id=org_id,
        report_id=report_id,
        report_fingerprint=report_fingerprint,
        accused_act_index=0,
        accused_act_sha256="c" * 64,
        patent_id="US1234567B2",
        claim_number=1,
        controlling_claim_text="1. A method of treating a patient with aspirin.",
        current_claim_receipt_sha256="d" * 64,
        controlling_claim_document_ids=["US1234567B2:grant-claims"],
        target_product_identity="aspirin",
        compound=compound,
        proposed_indication="Secondary prevention of myocardial infarction",
        proposed_label_use="75 mg orally once daily",
        label_carve_out_state="partial",
        issuer_user_id=attorney_id,
        verified_at=issued_at,
        evidence_references=["proposed-label-v7#section-1"],
        attestation_key_id="postgres-canary",
        attestation_key=_ATTESTATION_KEY,
    )
    return receipt.model_dump(mode="json")


@pytest.mark.asyncio
async def test_claimed_use_roles_enforce_unforgeable_writer_and_erasure_boundary() -> None:
    admin_engine = _engine("ADMIN_DATABASE_URL")
    api_engine = _engine("DATABASE_URL")
    worker_engine = _engine("WORKER_DATABASE_URL")
    writer_engine = _engine("CLAIMED_USE_WRITER_DATABASE_URL")
    erasure_engine = _engine("GLOBAL_ERASURE_DATABASE_URL")
    engines = [
        admin_engine,
        api_engine,
        worker_engine,
        writer_engine,
        erasure_engine,
    ]

    org_id = uuid.uuid4()
    attorney_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    report_id = f"claimed-boundary-{analysis_id.hex}"
    report_fingerprint = analysis_id.hex * 2
    issued_at = datetime.now(UTC)
    payload = _receipt_payload(
        analysis_id=analysis_id,
        org_id=org_id,
        attorney_id=attorney_id,
        report_id=report_id,
        report_fingerprint=report_fingerprint,
        issued_at=issued_at,
    )

    try:
        await verify_claimed_use_privilege_boundary()
        expected_role_states = (
            (api_engine, "praviar_api", False),
            (worker_engine, "praviar_worker", True),
            (writer_engine, "praviar_claimed_use_writer", False),
            (erasure_engine, "praviar_global_erasure", False),
        )
        for role_engine, principal, bypass_rls in expected_role_states:
            assert await _role_security_state(role_engine) == {
                "principal": principal,
                "is_superuser": False,
                "bypass_rls": bypass_rls,
                "inherits_privileges": False,
                "can_login": True,
                "membership_count": 0,
            }
        await _assert_protected_function_catalog_contract(admin_engine)

        async with admin_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES (:org_id, :clerk_org_id, 'Boundary Canary', :slug)
                    """
                ),
                {
                    "org_id": org_id,
                    "clerk_org_id": f"org_{org_id.hex}",
                    "slug": f"claimed-boundary-{org_id.hex}",
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, clerk_user_id, org_id, email, full_name, role
                    ) VALUES
                        (
                            :attorney_id, :attorney_clerk_id, :org_id,
                            :attorney_email, 'Boundary Attorney', 'attorney'
                        ),
                        (
                            :admin_id, :admin_clerk_id, :org_id,
                            :admin_email, 'Boundary Admin', 'admin'
                        )
                    """
                ),
                {
                    "attorney_id": attorney_id,
                    "attorney_clerk_id": f"user_{attorney_id.hex}",
                    "attorney_email": f"{attorney_id.hex}@canary.test",
                    "admin_id": admin_id,
                    "admin_clerk_id": f"user_{admin_id.hex}",
                    "admin_email": f"{admin_id.hex}@canary.test",
                    "org_id": org_id,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO analyses (
                        id, org_id, compound_input, initiated_by, config,
                        report_data, status, completed_at
                    ) VALUES (
                        :analysis_id, :org_id, 'aspirin', :attorney_id,
                        CAST(:config AS jsonb), CAST(:report_data AS jsonb),
                        'completed', clock_timestamp()
                    )
                    """
                ),
                {
                    "analysis_id": analysis_id,
                    "org_id": org_id,
                    "attorney_id": attorney_id,
                    "config": json.dumps(
                        {"product_context": {"accused_acts": [{"act": "regulatory_submission"}]}}
                    ),
                    "report_data": json.dumps(
                        {
                            "report_id": report_id,
                            "patent_details": {"US1234567B2": {}},
                        }
                    ),
                },
            )

        for runtime_engine in (api_engine, worker_engine):
            await _must_fail(
                runtime_engine,
                """
                INSERT INTO analysis_claimed_use_receipts (
                    analysis_id, org_id, report_id, report_fingerprint,
                    patent_id, claim_number, accused_act_index,
                    accused_act_sha256, receipt_sha256, receipt_payload,
                    issuer_user_id, issued_at
                ) VALUES (
                    :analysis_id, :org_id, :report_id, :report_fingerprint,
                    'US1234567B2', 1, 0, :accused_act_sha256,
                    :receipt_sha256, CAST(:payload AS jsonb),
                    :attorney_id, :issued_at
                )
                """,
                {
                    "analysis_id": analysis_id,
                    "org_id": org_id,
                    "report_id": report_id,
                    "report_fingerprint": report_fingerprint,
                    "accused_act_sha256": "c" * 64,
                    "receipt_sha256": payload["receipt_sha256"],
                    "payload": json.dumps(payload),
                    "attorney_id": attorney_id,
                    "issued_at": issued_at,
                },
            )
            await _must_fail(
                runtime_engine,
                "SELECT public.issue_claimed_use_receipt(CAST(:payload AS jsonb))",
                {"payload": json.dumps(payload)},
            )
            await _must_fail(
                runtime_engine,
                """
                INSERT INTO claimed_use_erasure_authorizations (
                    id, request_id, org_id, actor_kind, actor_user_id,
                    authorized_at, receipt_count
                ) VALUES (
                    :id, :request_id, :org_id, 'platform_superadmin',
                    :admin_id, now(), 1
                )
                """,
                {
                    "id": uuid.uuid4(),
                    "request_id": uuid.uuid4(),
                    "org_id": org_id,
                    "admin_id": admin_id,
                },
            )
            await _must_fail(runtime_engine, "SET ROLE praviar_global_erasure")
            await _must_fail(runtime_engine, "SET ROLE praviar_claimed_use_writer")

        payload_with_extra = {**payload, "unsigned_extra": "forbidden"}
        await _must_fail(
            writer_engine,
            "SELECT public.issue_claimed_use_receipt(CAST(:payload AS jsonb))",
            {"payload": json.dumps(payload_with_extra)},
        )

        async with writer_engine.begin() as connection:
            receipt_id = (
                await connection.execute(
                    text("SELECT public.issue_claimed_use_receipt(CAST(:payload AS jsonb))"),
                    {"payload": json.dumps(payload)},
                )
            ).scalar_one()

        for runtime_engine in (api_engine, worker_engine):
            await _must_fail(
                runtime_engine,
                """
                UPDATE analysis_claimed_use_receipts
                   SET revocation_reason = 'forged mutation'
                 WHERE id = :receipt_id
                """,
                {"receipt_id": receipt_id},
            )
            await _must_fail(
                runtime_engine,
                "DELETE FROM analysis_claimed_use_receipts WHERE id = :receipt_id",
                {"receipt_id": receipt_id},
            )
            await _must_fail(
                runtime_engine,
                """
                SELECT public.revoke_claimed_use_receipt(
                    :receipt_id, :org_id, :admin_id,
                    'Forged runtime revocation reason.', now()
                )
                """,
                {
                    "receipt_id": receipt_id,
                    "org_id": org_id,
                    "admin_id": admin_id,
                },
            )
            await _must_fail(
                runtime_engine,
                """
                SELECT public.erase_claimed_use_receipts(
                    :authorization_id, :request_id, :org_id, :admin_id,
                    :capability_secret
                )
                """,
                {
                    "authorization_id": uuid.uuid4(),
                    "request_id": uuid.uuid4(),
                    "org_id": org_id,
                    "admin_id": admin_id,
                    "capability_secret": "forged-capability-secret-value-000000",
                },
            )
            async with runtime_engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.execute(
                        text("SELECT set_config('app.current_org_id', :org_id, true)"),
                        {"org_id": str(org_id)},
                    )
                    await connection.execute(
                        text(
                            """
                            INSERT INTO audit_logs (
                                org_id, user_id, action, details, ip_address
                            ) VALUES (
                                :org_id, :admin_id,
                                'org.claimed_use_receipts_erasure_authorized',
                                '{}'::jsonb, ''
                            )
                            """
                        ),
                        {"org_id": org_id, "admin_id": admin_id},
                    )
                    await connection.execute(
                        text(
                            "SELECT set_config("
                            "'app.claimed_use_receipt_erasure_org_id', "
                            ":org_id, true)"
                        ),
                        {"org_id": str(org_id)},
                    )
                    with pytest.raises(SQLAlchemyError):
                        await connection.execute(
                            text(
                                "DELETE FROM analysis_claimed_use_receipts WHERE id = :receipt_id"
                            ),
                            {"receipt_id": receipt_id},
                        )
                finally:
                    await transaction.rollback()

        await _must_fail(
            writer_engine,
            """
            UPDATE analysis_claimed_use_receipts
               SET revocation_reason = 'forged mutation'
             WHERE id = :receipt_id
            """,
            {"receipt_id": receipt_id},
        )
        await _must_fail(
            writer_engine,
            "SELECT id FROM users WHERE org_id = :org_id",
            {"org_id": org_id},
        )
        await _must_fail(
            writer_engine,
            """
            UPDATE analyses
               SET compound_input = 'forged cross-purpose mutation'
             WHERE id = :analysis_id
            """,
            {"analysis_id": analysis_id},
        )
        await _must_fail(
            writer_engine,
            """
            SELECT public.erase_claimed_use_receipts(
                :authorization_id, :request_id, :org_id, :admin_id,
                :capability_secret
            )
            """,
            {
                "authorization_id": uuid.uuid4(),
                "request_id": uuid.uuid4(),
                "org_id": org_id,
                "admin_id": admin_id,
                "capability_secret": "forged-capability-secret-value-000000",
            },
        )
        await _must_fail(writer_engine, "SET ROLE praviar_global_erasure")
        await _must_fail(
            erasure_engine,
            "SELECT public.issue_claimed_use_receipt(CAST(:payload AS jsonb))",
            {"payload": json.dumps(payload)},
        )
        await _must_fail(
            erasure_engine,
            "DELETE FROM analysis_claimed_use_receipts WHERE id = :receipt_id",
            {"receipt_id": receipt_id},
        )
        await _must_fail(
            erasure_engine,
            "SELECT id FROM analysis_claimed_use_receipts WHERE id = :receipt_id",
            {"receipt_id": receipt_id},
        )
        await _must_fail(
            erasure_engine,
            "INSERT INTO claimed_use_erasure_capabilities "
            "(id, request_id, org_id, actor_kind, capability_sha256, "
            "authorized_at, expires_at) VALUES "
            "(:id, :request_id, :org_id, 'scheduled_system', :digest, now(), "
            "now() + interval '5 minutes')",
            {
                "id": uuid.uuid4(),
                "request_id": uuid.uuid4(),
                "org_id": org_id,
                "digest": "f" * 64,
            },
        )
        await _must_fail(erasure_engine, "SET ROLE praviar_claimed_use_writer")

        async with writer_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT public.revoke_claimed_use_receipt(
                        :receipt_id, :org_id, :admin_id,
                        'Counsel withdrew the affirmation.', now()
                    )
                    """
                ),
                {
                    "receipt_id": receipt_id,
                    "org_id": org_id,
                    "admin_id": admin_id,
                },
            )
            stored = (
                await connection.execute(
                    text(
                        """
                        SELECT receipt_payload, revoked_at, revoked_by_user_id
                          FROM analysis_claimed_use_receipts
                         WHERE id = :receipt_id
                        """
                    ),
                    {"receipt_id": receipt_id},
                )
            ).one()
        verified_receipt = ClaimedUseMatchReceipt.model_validate(stored.receipt_payload)
        assert verify_claimed_use_match_attestation(
            verified_receipt,
            attestation_key=_ATTESTATION_KEY,
        )
        assert stored.revoked_at is not None
        assert stored.revoked_by_user_id == admin_id

        authorization_id = uuid.uuid4()
        request_id = uuid.uuid4()
        capability_secret = "canary-capability-secret-value-000000000000"
        capability_sha256 = hashlib.sha256(capability_secret.encode("utf-8")).hexdigest()
        async with api_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT public.authorize_claimed_use_erasure(
                        :authorization_id, :request_id, :org_id,
                        'platform_superadmin', :admin_id, :capability_sha256
                    )
                    """
                ),
                {
                    "authorization_id": authorization_id,
                    "request_id": request_id,
                    "org_id": org_id,
                    "admin_id": admin_id,
                    "capability_sha256": capability_sha256,
                },
            )
        async with erasure_engine.begin() as connection:
            erased_count = (
                await connection.execute(
                    text(
                        """
                        SELECT public.erase_claimed_use_receipts(
                            :authorization_id, :request_id, :org_id,
                            :admin_id, :capability_secret
                        )
                        """
                    ),
                    {
                        "authorization_id": authorization_id,
                        "request_id": request_id,
                        "org_id": org_id,
                        "admin_id": admin_id,
                        "capability_secret": capability_secret,
                    },
                )
            ).scalar_one()
        assert erased_count == 1
        await _must_fail(
            erasure_engine,
            """
            SELECT public.erase_claimed_use_receipts(
                :authorization_id, :request_id, :org_id, :admin_id,
                :capability_secret
            )
            """,
            {
                "authorization_id": authorization_id,
                "request_id": request_id,
                "org_id": org_id,
                "admin_id": admin_id,
                "capability_secret": capability_secret,
            },
        )

        async with admin_engine.connect() as connection:
            authorization = (
                await connection.execute(
                    text(
                        """
                        SELECT org_id, actor_kind, actor_user_id, receipt_count
                          FROM claimed_use_erasure_authorizations
                         WHERE id = :authorization_id
                        """
                    ),
                    {"authorization_id": authorization_id},
                )
            ).one()
        assert authorization.org_id == org_id
        assert authorization.actor_kind == "platform_superadmin"
        assert authorization.actor_user_id == admin_id
        assert authorization.receipt_count == 1

        for mutation in (
            "UPDATE claimed_use_erasure_authorizations "
            "SET receipt_count = 0 WHERE id = :authorization_id",
            "DELETE FROM claimed_use_erasure_authorizations WHERE id = :authorization_id",
        ):
            await _must_fail(
                admin_engine,
                mutation,
                {"authorization_id": authorization_id},
            )
    finally:
        await dispose_claimed_use_privileged_engines()
        for engine in engines:
            await engine.dispose()

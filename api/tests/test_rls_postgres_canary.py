"""Real PostgreSQL RLS isolation canaries.

These tests intentionally require a migrated PostgreSQL database. They are run
by the dedicated CI isolation job, separate from the broad unit suite, so RLS
cannot quietly regress behind mocks or SQLite.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from conftest import valid_report_data, valid_report_data_for_patents
from praviar_pipeline.models.accused_acts import create_claimed_use_match_receipt
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.errors import APIError
from api.services.billing import resolve_credit_capacity_request_data
from api.services.offboarding import execute_org_erasure
from api.services.patents import get_patent_detail_for_org, list_patents_for_org
from api.services.report_content import load_report_for_org, search_report_for_org

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_RLS_TESTS") != "1",
    reason="real PostgreSQL RLS canaries run in the dedicated CI job",
)


def _claimed_use_receipt_payload(
    *,
    analysis_id: uuid.UUID,
    org_id: uuid.UUID,
    issuer_user_id: uuid.UUID,
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
        issuer_user_id=issuer_user_id,
        verified_at=issued_at,
        evidence_references=["proposed-label-v7#section-1"],
        attestation_key_id="postgres-canary",
        attestation_key=b"postgres-claimed-use-canary-key-32b",
    )
    return receipt.model_dump(mode="json")


@pytest.mark.asyncio
async def test_postgres_rejects_confirmed_identity_without_submitted_value() -> None:
    """Prove the migrated identity provenance CHECK rejects SQL NULL."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                await conn.execute(
                    text(
                        """
                        INSERT INTO organizations (id, clerk_org_id, name, slug)
                        VALUES (:org_id, :clerk_org_id, 'Identity Canary', :slug)
                        """
                    ),
                    {
                        "org_id": org_id,
                        "clerk_org_id": f"org_{org_id.hex}",
                        "slug": f"identity-canary-{org_id.hex}",
                    },
                )
                await conn.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, clerk_user_id, org_id, email, full_name, role
                        ) VALUES (
                            :user_id, :clerk_user_id, :org_id,
                            :email, 'Identity Canary', 'admin'
                        )
                        """
                    ),
                    {
                        "user_id": user_id,
                        "clerk_user_id": f"user_{user_id.hex}",
                        "org_id": org_id,
                        "email": f"{user_id.hex}@canary.test",
                    },
                )
                await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))

                savepoint = await conn.begin_nested()
                with pytest.raises(SQLAlchemyError):
                    await conn.execute(
                        text(
                            """
                            INSERT INTO analyses (
                                id, org_id, compound_input, input_type,
                                submitted_identity_confirmed,
                                submitted_identity_value, initiated_by
                            ) VALUES (
                                :analysis_id, :org_id, 'aspirin', 'name',
                                true, NULL, :user_id
                            )
                            """
                        ),
                        {
                            "analysis_id": uuid.uuid4(),
                            "org_id": org_id,
                            "user_id": user_id,
                        },
                    )
                await savepoint.rollback()

                valid_analysis_id = uuid.uuid4()
                await conn.execute(
                    text(
                        """
                        INSERT INTO analyses (
                            id, org_id, compound_input, input_type,
                            submitted_identity_confirmed,
                            submitted_identity_value, initiated_by
                        ) VALUES (
                            :analysis_id, :org_id, 'aspirin', 'name',
                            true, 'aspirin', :user_id
                        )
                        """
                    ),
                    {
                        "analysis_id": valid_analysis_id,
                        "org_id": org_id,
                        "user_id": user_id,
                    },
                )
                assert (
                    await conn.scalar(
                        text("SELECT count(*) FROM analyses WHERE id = :analysis_id"),
                        {"analysis_id": valid_analysis_id},
                    )
                    == 1
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


def _publishable_marker_report(*, report_id: str, marker: str) -> dict:
    report = valid_report_data(report_id=report_id)
    report["risk_summary"]["executive_summary"] = marker
    return report


def _patent_browser_report(*, patent_id: str, title: str, risk_level: str) -> dict:
    return valid_report_data_for_patents(
        patent_analyses=[
            {
                "patent_id": patent_id,
                "title": title,
                "assignee": "Praviar Canary",
                "risk_level": risk_level,
                "expiry_date": "2035-01-01",
            }
        ]
    )


@pytest.mark.asyncio
async def test_postgres_migration_owner_visibility_requires_no_force_rls_window() -> None:
    """Prove the c2 owner backfill/guard visibility contract on real PostgreSQL."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    row_org_id = uuid.uuid4()
    hidden_org_id = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TEMP TABLE c2_owner_visibility_canary "
                    "(org_id uuid NOT NULL, delivery_state text NOT NULL) ON COMMIT DROP"
                )
            )
            await conn.execute(
                text("ALTER TABLE c2_owner_visibility_canary ENABLE ROW LEVEL SECURITY")
            )
            await conn.execute(
                text(
                    "CREATE POLICY tenant_only ON c2_owner_visibility_canary "
                    "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO c2_owner_visibility_canary (org_id, delivery_state) "
                    "VALUES (:org_id, 'outcome_unknown')"
                ),
                {"org_id": row_org_id},
            )
            await conn.execute(
                select(func.set_config("app.current_org_id", str(hidden_org_id), True))
            )
            await conn.execute(
                text("ALTER TABLE c2_owner_visibility_canary FORCE ROW LEVEL SECURITY")
            )
            hidden = await conn.scalar(text("SELECT count(*) FROM c2_owner_visibility_canary"))
            assert hidden == 0

            await conn.execute(
                text("ALTER TABLE c2_owner_visibility_canary NO FORCE ROW LEVEL SECURITY")
            )
            owner_visible = await conn.scalar(
                text("SELECT count(*) FROM c2_owner_visibility_canary")
            )
            assert owner_visible == 1

            await conn.execute(
                text("ALTER TABLE c2_owner_visibility_canary FORCE ROW LEVEL SECURITY")
            )
            restored = await conn.scalar(text("SELECT count(*) FROM c2_owner_visibility_canary"))
            assert restored == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_organization_compound_usage_is_strictly_tenant_local() -> None:
    """Two tenants sharing one global identity must see only their own usage."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    compound_id = uuid.uuid4()
    first_a = datetime(2026, 1, 5, tzinfo=UTC)
    first_b = datetime(2026, 6, 9, tzinfo=UTC)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                for org_id, suffix in ((org_a, "a"), (org_b, "b")):
                    await conn.execute(
                        text(
                            """
                            INSERT INTO organizations (id, clerk_org_id, name, slug)
                            VALUES (:org_id, :clerk_org_id, :name, :slug)
                            """
                        ),
                        {
                            "org_id": org_id,
                            "clerk_org_id": f"org_compound_canary_{org_id.hex}",
                            "name": f"Compound Canary {suffix.upper()}",
                            "slug": f"compound-canary-{suffix}-{org_id.hex}",
                        },
                    )
                await conn.execute(
                    text(
                        """
                        INSERT INTO compounds (
                            id, canonical_smiles, inchi_key, name,
                            molecular_formula, analysis_count
                        ) VALUES (
                            :compound_id, 'CCO', :inchi_key, 'Ethanol', 'C2H6O', 999
                        )
                        """
                    ),
                    {
                        "compound_id": compound_id,
                        "inchi_key": f"{compound_id.hex[:14].upper()}-UHFFFAOYSA-N",
                    },
                )

                await conn.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
                await conn.execute(
                    text(
                        """
                        INSERT INTO organization_compounds (
                            org_id, compound_id, display_name,
                            first_analyzed_at, analysis_count
                        ) VALUES (
                            :org_id, :compound_id, :display_name,
                            :first_analyzed_at, 2
                        )
                        """
                    ),
                    {
                        "org_id": org_a,
                        "compound_id": compound_id,
                        "display_name": "Tenant A Project Name",
                        "first_analyzed_at": first_a,
                    },
                )
                await conn.execute(select(func.set_config("app.current_org_id", str(org_b), True)))
                await conn.execute(
                    text(
                        """
                        INSERT INTO organization_compounds (
                            org_id, compound_id, display_name,
                            first_analyzed_at, analysis_count
                        ) VALUES (
                            :org_id, :compound_id, :display_name,
                            :first_analyzed_at, 7
                        )
                        """
                    ),
                    {
                        "org_id": org_b,
                        "compound_id": compound_id,
                        "display_name": "Tenant B Project Name",
                        "first_analyzed_at": first_b,
                    },
                )

                await conn.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
                visible_a = (
                    await conn.execute(
                        text(
                            """
                            SELECT display_name, first_analyzed_at, analysis_count
                            FROM organization_compounds
                            WHERE compound_id = :compound_id
                            """
                        ),
                        {"compound_id": compound_id},
                    )
                ).one()
                assert visible_a.display_name == "Tenant A Project Name"
                assert visible_a.first_analyzed_at == first_a
                assert visible_a.analysis_count == 2
                hidden_b = await conn.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM organization_compounds
                        WHERE org_id = :org_b
                        """
                    ),
                    {"org_b": org_b},
                )
                assert hidden_b == 0

                await conn.execute(select(func.set_config("app.current_org_id", str(org_b), True)))
                visible_b = (
                    await conn.execute(
                        text(
                            """
                            SELECT display_name, first_analyzed_at, analysis_count
                            FROM organization_compounds
                            WHERE compound_id = :compound_id
                            """
                        ),
                        {"compound_id": compound_id},
                    )
                ).one()
                assert visible_b.display_name == "Tenant B Project Name"
                assert visible_b.first_analyzed_at == first_b
                assert visible_b.analysis_count == 7
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_weekly_digest_capability_lookup_is_exact_and_tenant_safe() -> None:
    """Prove public capability lookup reveals exactly one matching delivery."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = uuid.uuid4()
    delivery_id = uuid.uuid4()
    capability_digest = "a" * 64
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                for org_id, suffix in ((org_a, "a"), (org_b, "b")):
                    await conn.execute(
                        text(
                            """
                            INSERT INTO organizations (id, clerk_org_id, name, slug)
                            VALUES (:org_id, :clerk_org_id, :name, :slug)
                            """
                        ),
                        {
                            "org_id": org_id,
                            "clerk_org_id": f"org_digest_canary_{org_id.hex}",
                            "name": f"Digest Canary {suffix.upper()}",
                            "slug": f"digest-canary-{suffix}-{org_id.hex}",
                        },
                    )
                await conn.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
                await conn.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, clerk_user_id, org_id, email, full_name, role
                        ) VALUES (
                            :user_id, :clerk_user_id, :org_id, :email,
                            'Digest Canary', 'attorney'
                        )
                        """
                    ),
                    {
                        "user_id": user_a,
                        "clerk_user_id": f"user_{user_a.hex}",
                        "org_id": org_a,
                        "email": f"{user_a.hex}@canary.test",
                    },
                )
                await conn.execute(
                    text(
                        """
                        INSERT INTO weekly_digest_deliveries (
                            id, org_id, user_id, period_start, period_end,
                            state, submission_id,
                            unsubscribe_token_digest, unsubscribe_expires_at,
                            provider_attempt_started_at, provider_accepted_at,
                            provider_message_id
                        ) VALUES (
                            :delivery_id, :org_id, :user_id,
                            '2026-07-06 09:00:00+00',
                            '2026-07-13 09:00:00+00',
                            'provider_accepted', :submission_id,
                            :capability_digest, now() + interval '1 day',
                            now(), now(), 'digest-canary-message'
                        )
                        """
                    ),
                    {
                        "delivery_id": delivery_id,
                        "org_id": org_a,
                        "user_id": user_a,
                        "submission_id": "d" * 64,
                        "capability_digest": capability_digest,
                    },
                )

                await conn.execute(select(func.set_config("app.current_org_id", str(org_b), True)))
                hidden_from_other_tenant = await conn.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM weekly_digest_deliveries
                        WHERE id = :delivery_id
                        """
                    ),
                    {"delivery_id": delivery_id},
                )
                assert hidden_from_other_tenant == 0

                await conn.execute(select(func.set_config("app.current_org_id", "", True)))
                await conn.execute(
                    select(
                        func.set_config(
                            "app.digest_unsubscribe_token_digest",
                            "b" * 64,
                            True,
                        )
                    )
                )
                wrong_capability = await conn.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM weekly_digest_deliveries
                        WHERE unsubscribe_token_digest = :capability_digest
                        """
                    ),
                    {"capability_digest": capability_digest},
                )
                assert wrong_capability == 0

                await conn.execute(
                    select(
                        func.set_config(
                            "app.digest_unsubscribe_token_digest",
                            capability_digest,
                            True,
                        )
                    )
                )
                exact_capability = await conn.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM weekly_digest_deliveries
                        WHERE unsubscribe_token_digest = :capability_digest
                        """
                    ),
                    {"capability_digest": capability_digest},
                )
                assert exact_capability == 1
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_org_erasure_preserves_declined_request_constraint() -> None:
    """Prove erasure redacts declined notes without violating the DB constraint."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_id = uuid.uuid4()
    compound_id = uuid.uuid4()

    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES (:org_id, :clerk_org_id, 'Erasure Canary', :slug)
                    """
                ),
                {
                    "org_id": org_id,
                    "clerk_org_id": f"org_{org_id.hex}",
                    "slug": f"erasure-canary-{org_id.hex}",
                },
            )
            await session.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            await session.execute(
                text(
                    """
                    INSERT INTO compounds (
                        id, canonical_smiles, inchi_key, name,
                        molecular_formula, analysis_count
                    ) VALUES (
                        :compound_id, 'CCO', :inchi_key, 'Ethanol', 'C2H6O', 1
                    )
                    """
                ),
                {
                    "compound_id": compound_id,
                    "inchi_key": f"{compound_id.hex[:14].upper()}-UHFFFAOYSA-N",
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO organization_compounds (
                        org_id, compound_id, display_name,
                        first_analyzed_at, analysis_count
                    ) VALUES (:org_id, :compound_id, 'Ethanol', now(), 1)
                    """
                ),
                {"org_id": org_id, "compound_id": compound_id},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO users (
                        id, clerk_user_id, org_id, email, full_name, role
                    ) VALUES (
                        :user_id, :clerk_user_id, :org_id, :email,
                        'Erasure Canary Admin', 'admin'
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "clerk_user_id": f"user_{user_id.hex}",
                    "org_id": org_id,
                    "email": f"{user_id.hex}@canary.test",
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO credit_capacity_requests (
                        id, org_id, requester_user_id, requester_name,
                        requested_reports, source, status, notified_admins,
                        resolved_at, resolved_by_user_id, resolution_note
                    ) VALUES (
                        :request_id, :org_id, :user_id, 'Sensitive Name',
                        5, 'analysis_launch', 'declined', 1,
                        now(), :user_id, 'Sensitive decline reason'
                    )
                    """
                ),
                {
                    "request_id": request_id,
                    "org_id": org_id,
                    "user_id": user_id,
                },
            )

            async def flush_instead_of_commit() -> None:
                await session.flush()

            with patch.object(
                session,
                "commit",
                new=AsyncMock(side_effect=flush_instead_of_commit),
            ):
                await execute_org_erasure(
                    session,
                    org_id=org_id,
                    executed_by_user_id=user_id,
                    executed_by_email="canary-admin@example.com",
                )

            redacted = (
                await session.execute(
                    text(
                        """
                        SELECT requester_name, resolution_note
                        FROM credit_capacity_requests
                        WHERE id = :request_id
                        """
                    ),
                    {"request_id": request_id},
                )
            ).one()
            assert redacted.requester_name == "[ERASED]"
            assert redacted.resolution_note == "[ERASED]"
            association_count = await session.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM organization_compounds
                    WHERE compound_id = :compound_id
                    """
                ),
                {"compound_id": compound_id},
            )
            assert association_count == 0
            global_identity_count = await session.scalar(
                text("SELECT count(*) FROM compounds WHERE id = :compound_id"),
                {"compound_id": compound_id},
            )
            assert global_identity_count == 1
            await session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_launch_lock_precedes_manual_capacity_verification() -> None:
    """Prove verification re-reads capacity after a concurrent launch commits."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    org_id = uuid.uuid4()
    requester_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    request_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    verification_task: asyncio.Task | None = None

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (
                        id, clerk_org_id, name, slug, plan,
                        max_analyses_per_month, free_analyses_remaining
                    ) VALUES (
                        :org_id, :clerk_org_id, 'Capacity Lock Canary', :slug,
                        'free', 1, 1
                    )
                    """
                ),
                {
                    "org_id": org_id,
                    "clerk_org_id": f"org_{org_id.hex}",
                    "slug": f"capacity-lock-canary-{org_id.hex}",
                },
            )
            await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            await conn.execute(
                text(
                    """
                    INSERT INTO users (
                        id, clerk_user_id, org_id, email, full_name, role
                    ) VALUES
                      (
                        :requester_id, :requester_clerk, :org_id,
                        :requester_email, 'Capacity Requester', 'scientist'
                      ),
                      (
                        :admin_id, :admin_clerk, :org_id,
                        :admin_email, 'Capacity Admin', 'admin'
                      )
                    """
                ),
                {
                    "requester_id": requester_id,
                    "requester_clerk": f"user_{requester_id.hex}",
                    "requester_email": f"{requester_id.hex}@canary.test",
                    "admin_id": admin_id,
                    "admin_clerk": f"user_{admin_id.hex}",
                    "admin_email": f"{admin_id.hex}@canary.test",
                    "org_id": org_id,
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO credit_capacity_requests (
                        id, org_id, requester_user_id, requester_name,
                        requested_reports, source, status, notified_admins
                    ) VALUES (
                        :request_id, :org_id, :requester_id,
                        'Capacity Requester', 1, 'analysis_launch', 'pending', 1
                    )
                    """
                ),
                {
                    "request_id": request_id,
                    "org_id": org_id,
                    "requester_id": requester_id,
                },
            )

        async with session_factory() as launch_session, session_factory() as verify_session:
            await launch_session.execute(
                select(func.set_config("app.current_org_id", str(org_id), True))
            )
            await launch_session.execute(
                text("SELECT id FROM organizations WHERE id = :org_id FOR UPDATE"),
                {"org_id": org_id},
            )
            await launch_session.execute(
                text(
                    """
                    INSERT INTO analyses (
                        id, org_id, compound_input, initiated_by
                    ) VALUES (
                        :analysis_id, :org_id, 'capacity-lock-canary', :requester_id
                    )
                    """
                ),
                {
                    "analysis_id": analysis_id,
                    "org_id": org_id,
                    "requester_id": requester_id,
                },
            )

            async def verify_capacity() -> dict[str, object]:
                await verify_session.execute(
                    select(func.set_config("app.current_org_id", str(org_id), True))
                )
                return await resolve_credit_capacity_request_data(
                    verify_session,
                    user=SimpleNamespace(id=admin_id, org_id=org_id),
                    request_id=request_id,
                    resolution_status="fulfilled",
                    note="Current capacity checked.",
                    request=None,
                )

            verification_task = asyncio.create_task(verify_capacity())
            _done, pending = await asyncio.wait(
                {verification_task},
                timeout=0.1,
            )
            assert verification_task in pending

            await launch_session.commit()
            with pytest.raises(APIError) as exc_info:
                await asyncio.wait_for(verification_task, timeout=5)
            assert exc_info.value.status == 409
            assert exc_info.value.type_uri == (
                "https://problems.praviar.invalid/insufficient-capacity"
            )
            await verify_session.rollback()
    finally:
        if verification_task is not None and not verification_task.done():
            verification_task.cancel()
            with suppress(asyncio.CancelledError):
                await verification_task
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            await conn.execute(
                text("DELETE FROM organizations WHERE id = :org_id"),
                {"org_id": org_id},
            )
        await engine.dispose()


async def _assert_sql_rejected(conn, statement: str, params: dict | None = None) -> None:
    savepoint = await conn.begin_nested()
    try:
        with pytest.raises(SQLAlchemyError):
            await conn.execute(text(statement), params or {})
    finally:
        await savepoint.rollback()


async def _assert_sql_mutation_denied(conn, statement: str, params: dict | None = None) -> None:
    """Assert RLS silently denied a mutation by hiding every target row."""
    result = await conn.execute(text(statement), params or {})
    assert result.rowcount == 0


@pytest.mark.asyncio
async def test_postgres_credit_ledger_and_api_key_capability_canaries() -> None:
    """Exercise append-only ledger and exact-HMAC API-key RLS on PostgreSQL."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    analysis_a = uuid.uuid4()
    ledger_id = uuid.uuid4()
    api_key_a = uuid.uuid4()
    api_key_b = uuid.uuid4()
    hash_a = "a" * 64
    hash_b = "b" * 64
    transaction = None

    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES
                      (:org_a, :clerk_a, 'Ledger Canary A', :slug_a),
                      (:org_b, :clerk_b, 'Ledger Canary B', :slug_b)
                    """
                ),
                {
                    "org_a": org_a,
                    "org_b": org_b,
                    "clerk_a": f"org_{org_a.hex}",
                    "clerk_b": f"org_{org_b.hex}",
                    "slug_a": f"ledger-canary-a-{org_a.hex}",
                    "slug_b": f"ledger-canary-b-{org_b.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, clerk_user_id, org_id, email, full_name, role)
                    VALUES
                      (:user_a, :clerk_a, :org_a, :email_a, 'Canary A', 'admin'),
                      (:user_b, :clerk_b, :org_b, :email_b, 'Canary B', 'admin')
                    """
                ),
                {
                    "user_a": user_a,
                    "user_b": user_b,
                    "org_a": org_a,
                    "org_b": org_b,
                    "clerk_a": f"user_{user_a.hex}",
                    "clerk_b": f"user_{user_b.hex}",
                    "email_a": f"{user_a.hex}@canary.test",
                    "email_b": f"{user_b.hex}@canary.test",
                },
            )

            await conn.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
            await conn.execute(
                text(
                    """
                    INSERT INTO analyses (id, org_id, compound_input, initiated_by)
                    VALUES (:analysis_id, :org_id, 'ledger-canary', :user_id)
                    """
                ),
                {"analysis_id": analysis_a, "org_id": org_a, "user_id": user_a},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO analysis_credit_ledger (
                        id, org_id, user_id, analysis_id, kind, credits_delta, details
                    ) VALUES (
                        :id, :org_id, :user_id, :analysis_id, 'consume', -1,
                        CAST(:details AS jsonb)
                    )
                    """
                ),
                {
                    "id": ledger_id,
                    "org_id": org_a,
                    "user_id": user_a,
                    "analysis_id": analysis_a,
                    "details": json.dumps({"reservation_id": f"r-{ledger_id.hex}"}),
                },
            )
            assert (
                await conn.execute(
                    text("SELECT id FROM analysis_credit_ledger WHERE id = :id"),
                    {"id": ledger_id},
                )
            ).scalar_one() == ledger_id

            await _assert_sql_mutation_denied(
                conn,
                "UPDATE analysis_credit_ledger SET credits_delta = -2 WHERE id = :id",
                {"id": ledger_id},
            )
            assert (
                await conn.execute(
                    text("SELECT credits_delta FROM analysis_credit_ledger WHERE id = :id"),
                    {"id": ledger_id},
                )
            ).scalar_one() == -1
            await _assert_sql_mutation_denied(
                conn,
                "DELETE FROM analysis_credit_ledger WHERE id = :id",
                {"id": ledger_id},
            )
            assert (
                await conn.execute(
                    text("SELECT count(*) FROM analysis_credit_ledger WHERE id = :id"),
                    {"id": ledger_id},
                )
            ).scalar_one() == 1
            assert (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_trigger "
                        "WHERE tgname = 'trg_analysis_credit_ledger_append_only' "
                        "AND NOT tgisinternal"
                    )
                )
            ).scalar_one() == 1
            await _assert_sql_rejected(
                conn,
                """
                INSERT INTO analysis_credit_ledger
                    (id, org_id, kind, credits_delta, details)
                VALUES (:id, :org_id, 'consume', 1, '{}'::jsonb)
                """,
                {"id": uuid.uuid4(), "org_id": org_a},
            )
            await conn.execute(select(func.set_config("app.current_org_id", str(org_b), True)))
            await _assert_sql_rejected(
                conn,
                """
                INSERT INTO analysis_credit_ledger
                    (id, org_id, analysis_id, kind, credits_delta, details)
                VALUES (:id, :org_id, :analysis_id, 'refund', 1, '{}'::jsonb)
                """,
                {"id": uuid.uuid4(), "org_id": org_b, "analysis_id": analysis_a},
            )

            expires_at = datetime.now(UTC) + timedelta(days=30)
            for key_id, org_id, user_id, digest, prefix in (
                (api_key_a, org_a, user_a, hash_a, "prv_live_abcdefghijk..."),
                (api_key_b, org_b, user_b, hash_b, "prv_live_lmnopqrstuv..."),
            ):
                await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
                await conn.execute(
                    text(
                        """
                        INSERT INTO api_keys (
                            id, org_id, user_id, name, key_hash, key_prefix,
                            scopes, expires_at, revoked
                        ) VALUES (
                            :id, :org_id, :user_id, 'canary', :key_hash, :key_prefix,
                            '["analyses:read"]'::jsonb, :expires_at, false
                        )
                        """
                    ),
                    {
                        "id": key_id,
                        "org_id": org_id,
                        "user_id": user_id,
                        "key_hash": digest,
                        "key_prefix": prefix,
                        "expires_at": expires_at,
                    },
                )

            await conn.execute(select(func.set_config("app.current_org_id", "", True)))
            await conn.execute(select(func.set_config("app.api_key_hash", hash_a, True)))
            visible = (
                (await conn.execute(text("SELECT id FROM api_keys ORDER BY id"))).scalars().all()
            )
            assert visible == [api_key_a]

            await conn.execute(select(func.set_config("app.api_key_hash", "", True)))
            await conn.execute(
                select(func.set_config("app.api_key_prefix", "prv_live_abcdefghijk...", True))
            )
            assert (await conn.execute(text("SELECT id FROM api_keys"))).scalars().all() == []

            await transaction.rollback()
            transaction = None
    finally:
        if transaction is not None and transaction.is_active:
            await transaction.rollback()
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_rls_filters_and_rejects_cross_org_rows() -> None:
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    analysis_a = uuid.uuid4()
    analysis_b = uuid.uuid4()
    report_marker_a = f"tenant-a-report-marker-{analysis_a.hex}"
    report_marker_b = f"tenant-b-report-marker-{analysis_b.hex}"
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES
                      (:org_a, :clerk_org_a, 'Tenant A', :slug_a),
                      (:org_b, :clerk_org_b, 'Tenant B', :slug_b)
                    """
                ),
                {
                    "org_a": org_a,
                    "org_b": org_b,
                    "clerk_org_a": f"org_{org_a.hex}",
                    "clerk_org_b": f"org_{org_b.hex}",
                    "slug_a": f"tenant-a-{org_a.hex}",
                    "slug_b": f"tenant-b-{org_b.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, clerk_user_id, org_id, email, full_name, role)
                    VALUES
                      (:user_a, :clerk_user_a, :org_a, 'a@example.test', 'User A', 'admin'),
                      (:user_b, :clerk_user_b, :org_b, 'b@example.test', 'User B', 'admin')
                    """
                ),
                {
                    "user_a": user_a,
                    "user_b": user_b,
                    "clerk_user_a": f"user_{user_a.hex}",
                    "clerk_user_b": f"user_{user_b.hex}",
                    "org_a": org_a,
                    "org_b": org_b,
                },
            )

        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
            await conn.execute(
                text(
                    """
                    INSERT INTO analyses (
                        id,
                        org_id,
                        compound_input,
                        initiated_by,
                        report_data,
                        status,
                        completed_at
                    )
                    VALUES (
                        :analysis_id,
                        :org_id,
                        'aspirin',
                        :user_id,
                        CAST(:report_data AS jsonb),
                        'completed',
                        clock_timestamp()
                    )
                    """
                ),
                {
                    "analysis_id": analysis_a,
                    "org_id": org_a,
                    "user_id": user_a,
                    "report_data": json.dumps(
                        _publishable_marker_report(
                            report_id=f"rls-canary-a-{analysis_a.hex}",
                            marker=report_marker_a,
                        )
                    ),
                },
            )

        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_b), True)))
            await conn.execute(
                text(
                    """
                    INSERT INTO analyses (
                        id,
                        org_id,
                        compound_input,
                        initiated_by,
                        report_data,
                        status,
                        completed_at
                    )
                    VALUES (
                        :analysis_id,
                        :org_id,
                        'ibuprofen',
                        :user_id,
                        CAST(:report_data AS jsonb),
                        'completed',
                        clock_timestamp()
                    )
                    """
                ),
                {
                    "analysis_id": analysis_b,
                    "org_id": org_b,
                    "user_id": user_b,
                    "report_data": json.dumps(
                        _publishable_marker_report(
                            report_id=f"rls-canary-b-{analysis_b.hex}",
                            marker=report_marker_b,
                        )
                    ),
                },
            )

        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
            rows = (
                (await conn.execute(text("SELECT id FROM analyses ORDER BY compound_input")))
                .scalars()
                .all()
            )
            assert rows == [analysis_a]
            report_summaries = (
                (
                    await conn.execute(
                        text(
                            """
                        SELECT report_data -> 'risk_summary' ->> 'executive_summary'
                        FROM analyses
                        ORDER BY compound_input
                        """
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert report_summaries == [report_marker_a]
            direct_report = (
                await conn.execute(
                    text(
                        """
                        SELECT report_data -> 'risk_summary' ->> 'executive_summary'
                        FROM analyses
                        WHERE id = :analysis_id
                        """
                    ),
                    {"analysis_id": analysis_b},
                )
            ).scalar_one_or_none()
            assert direct_report is None
            report_search_rows = (
                (
                    await conn.execute(
                        text("SELECT id FROM analyses WHERE report_data::text ILIKE :needle"),
                        {"needle": f"%{report_marker_b}%"},
                    )
                )
                .scalars()
                .all()
            )
            assert report_search_rows == []

        async with session_factory() as session, session.begin():
            await session.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
            search_results = await search_report_for_org(
                session,
                analysis_id=analysis_a,
                org_id=org_a,
                query_text=report_marker_a,
            )
            assert search_results["total"] > 0
            assert report_marker_a in str(search_results["results"])

            with pytest.raises(APIError) as exc_info:
                await search_report_for_org(
                    session,
                    analysis_id=analysis_b,
                    org_id=org_a,
                    query_text=report_marker_b,
                )
            assert exc_info.value.status == 404

        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_b), True)))
            rows = (
                (await conn.execute(text("SELECT id FROM analyses ORDER BY compound_input")))
                .scalars()
                .all()
            )
            assert rows == [analysis_b]
            report_summaries = (
                (
                    await conn.execute(
                        text(
                            """
                        SELECT report_data -> 'risk_summary' ->> 'executive_summary'
                        FROM analyses
                        ORDER BY compound_input
                        """
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert report_summaries == [report_marker_b]
            direct_report = (
                await conn.execute(
                    text(
                        """
                        SELECT report_data -> 'risk_summary' ->> 'executive_summary'
                        FROM analyses
                        WHERE id = :analysis_id
                        """
                    ),
                    {"analysis_id": analysis_a},
                )
            ).scalar_one_or_none()
            assert direct_report is None
            report_search_rows = (
                (
                    await conn.execute(
                        text("SELECT id FROM analyses WHERE report_data::text ILIKE :needle"),
                        {"needle": f"%{report_marker_a}%"},
                    )
                )
                .scalars()
                .all()
            )
            assert report_search_rows == []

        async with session_factory() as session, session.begin():
            await session.execute(select(func.set_config("app.current_org_id", str(org_b), True)))
            search_results = await search_report_for_org(
                session,
                analysis_id=analysis_b,
                org_id=org_b,
                query_text=report_marker_b,
            )
            assert search_results["total"] > 0
            assert report_marker_b in str(search_results["results"])

            with pytest.raises(APIError) as exc_info:
                await search_report_for_org(
                    session,
                    analysis_id=analysis_a,
                    org_id=org_b,
                    query_text=report_marker_a,
                )
            assert exc_info.value.status == 404

        async with engine.begin() as conn:
            rows = (await conn.execute(text("SELECT id FROM analyses"))).scalars().all()
            assert rows == []

        with pytest.raises(Exception, match="row-level security|violates row-level security"):
            async with engine.begin() as conn:
                await conn.execute(select(func.set_config("app.current_org_id", str(org_a), True)))
                await conn.execute(
                    text(
                        """
                        INSERT INTO analyses (id, org_id, compound_input, initiated_by)
                        VALUES (:analysis_id, :org_id, 'naproxen', :user_id)
                        """
                    ),
                    {"analysis_id": uuid.uuid4(), "org_id": org_b, "user_id": user_b},
                )
    finally:
        for org_id, analysis_id in ((org_a, analysis_a), (org_b, analysis_b)):
            async with engine.begin() as conn:
                await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
                await conn.execute(
                    text("DELETE FROM analyses WHERE id = :analysis_id"),
                    {"analysis_id": analysis_id},
                )
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id IN (:user_a, :user_b)"),
                {"user_a": user_a, "user_b": user_b},
            )
            await conn.execute(
                text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"),
                {"org_a": org_a, "org_b": org_b},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_claimed_use_receipt_payload_and_deletion_guards() -> None:
    """The database must reject malformed receipts and ordinary deletion."""
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    receipt_id = uuid.uuid4()
    issued_at = datetime.now(UTC)
    report_id = f"claimed-use-{analysis_id.hex}"
    report_fingerprint = analysis_id.hex * 2
    insert_receipt_sql = text(
        """
        INSERT INTO analysis_claimed_use_receipts (
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
            :receipt_id,
            :analysis_id,
            :org_id,
            :report_id,
            :report_fingerprint,
            'US1234567B2',
            1,
            0,
            :accused_act_sha256,
            :receipt_sha256,
            CAST(:receipt_payload AS jsonb),
            :issuer_user_id,
            :issued_at
        )
        """
    )

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES (:org_id, :clerk_org_id, 'Claimed Use Canary', :slug)
                    """
                ),
                {
                    "org_id": org_id,
                    "clerk_org_id": f"org_{org_id.hex}",
                    "slug": f"claimed-use-canary-{org_id.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (
                        id, clerk_user_id, org_id, email, full_name, role
                    ) VALUES (
                        :user_id, :clerk_user_id, :org_id,
                        :email, 'Claimed Use Attorney', 'attorney'
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "clerk_user_id": f"user_{user_id.hex}",
                    "org_id": org_id,
                    "email": f"{user_id.hex}@canary.test",
                },
            )

        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            await conn.execute(
                text(
                    """
                    INSERT INTO analyses (
                        id,
                        org_id,
                        compound_input,
                        initiated_by,
                        config,
                        report_data,
                        status,
                        completed_at
                    ) VALUES (
                        :analysis_id,
                        :org_id,
                        'aspirin',
                        :user_id,
                        CAST(:config AS jsonb),
                        CAST(:report_data AS jsonb),
                        'completed',
                        clock_timestamp()
                    )
                    """
                ),
                {
                    "analysis_id": analysis_id,
                    "org_id": org_id,
                    "user_id": user_id,
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

            valid_payload = _claimed_use_receipt_payload(
                analysis_id=analysis_id,
                org_id=org_id,
                issuer_user_id=user_id,
                report_id=report_id,
                report_fingerprint=report_fingerprint,
                issued_at=issued_at,
            )
            missing_literal = dict(valid_payload)
            missing_literal.pop("reviewer_role")
            false_attestation = {**valid_payload, "claimed_use_match": False}
            wrong_time = {
                **valid_payload,
                "verified_at": (issued_at + timedelta(minutes=5)).isoformat(),
            }
            naive_time = {
                **valid_payload,
                "verified_at": issued_at.replace(tzinfo=None).isoformat(),
            }
            malformed_payloads: list[object] = [
                [],
                missing_literal,
                false_attestation,
                wrong_time,
                naive_time,
            ]

            for malformed_payload in malformed_payloads:
                savepoint = await conn.begin_nested()
                with pytest.raises(SQLAlchemyError):
                    await conn.execute(
                        insert_receipt_sql,
                        {
                            "receipt_id": receipt_id,
                            "analysis_id": analysis_id,
                            "org_id": org_id,
                            "report_id": report_id,
                            "report_fingerprint": report_fingerprint,
                            "accused_act_sha256": "c" * 64,
                            "receipt_sha256": valid_payload["receipt_sha256"],
                            "receipt_payload": json.dumps(malformed_payload),
                            "issuer_user_id": user_id,
                            "issued_at": issued_at,
                        },
                    )
                await savepoint.rollback()

            await conn.execute(
                insert_receipt_sql,
                {
                    "receipt_id": receipt_id,
                    "analysis_id": analysis_id,
                    "org_id": org_id,
                    "report_id": report_id,
                    "report_fingerprint": report_fingerprint,
                    "accused_act_sha256": "c" * 64,
                    "receipt_sha256": valid_payload["receipt_sha256"],
                    "receipt_payload": json.dumps(valid_payload),
                    "issuer_user_id": user_id,
                    "issued_at": issued_at,
                },
            )

            direct_delete = await conn.begin_nested()
            with pytest.raises(SQLAlchemyError):
                await conn.execute(
                    text("DELETE FROM analysis_claimed_use_receipts WHERE id = :receipt_id"),
                    {"receipt_id": receipt_id},
                )
            await direct_delete.rollback()

            parent_delete = await conn.begin_nested()
            with pytest.raises(SQLAlchemyError):
                await conn.execute(
                    text("DELETE FROM analyses WHERE id = :analysis_id"),
                    {"analysis_id": analysis_id},
                )
            await parent_delete.rollback()

            await conn.execute(
                text(
                    """
                    INSERT INTO audit_logs (
                        id,
                        org_id,
                        user_id,
                        action,
                        details,
                        ip_address
                    ) VALUES (
                        :audit_id,
                        :org_id,
                        :user_id,
                        'org.claimed_use_receipts_erasure_authorized',
                        '{}'::jsonb,
                        ''
                    )
                    """
                ),
                {
                    "audit_id": uuid.uuid4(),
                    "org_id": org_id,
                    "user_id": user_id,
                },
            )
            await conn.execute(
                select(
                    func.set_config(
                        "app.claimed_use_receipt_erasure_org_id",
                        str(org_id),
                        True,
                    )
                )
            )
            forged_authorization = await conn.begin_nested()
            with pytest.raises(SQLAlchemyError):
                await conn.execute(
                    text("DELETE FROM analysis_claimed_use_receipts WHERE id = :receipt_id"),
                    {"receipt_id": receipt_id},
                )
            await forged_authorization.rollback()
            remaining = await conn.scalar(
                text("SELECT count(*) FROM analysis_claimed_use_receipts WHERE id = :receipt_id"),
                {"receipt_id": receipt_id},
            )
            assert remaining == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_report_data", [[], "scalar-report", None])
async def test_postgres_report_cache_denies_non_object_persisted_report_payloads(
    bad_report_data: object,
) -> None:
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES (:org_id, :clerk_org_id, 'Cache Canary Tenant', :slug)
                    """
                ),
                {
                    "org_id": org_id,
                    "clerk_org_id": f"org_{org_id.hex}",
                    "slug": f"cache-canary-{org_id.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, clerk_user_id, org_id, email, full_name, role)
                    VALUES (:user_id, :clerk_user_id, :org_id, 'cache-canary@example.test', 'Cache Canary', 'admin')
                    """
                ),
                {
                    "user_id": user_id,
                    "clerk_user_id": f"user_{user_id.hex}",
                    "org_id": org_id,
                },
            )

        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            await conn.execute(
                text(
                    """
                    INSERT INTO analyses (
                        id,
                        org_id,
                        compound_input,
                        initiated_by,
                        report_data,
                        status,
                        completed_at
                    )
                    VALUES (
                        :analysis_id,
                        :org_id,
                        'cache-canary-compound',
                        :user_id,
                        CAST(:report_data AS jsonb),
                        'completed',
                        clock_timestamp()
                    )
                    """
                ),
                {
                    "analysis_id": analysis_id,
                    "org_id": org_id,
                    "user_id": user_id,
                    "report_data": json.dumps(bad_report_data),
                },
            )

        async with session_factory() as session, session.begin():
            await session.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            with (
                patch(
                    "api.services.report_content.get_cached_report",
                    new=AsyncMock(return_value=valid_report_data(report_id="stale-cache-hit")),
                ) as get_cache,
                pytest.raises(APIError) as exc_info,
            ):
                await load_report_for_org(session, analysis_id=analysis_id, org_id=org_id)

            assert exc_info.value.status == 404
            assert "Report not yet available" in str(exc_info.value)
            get_cache.assert_not_awaited()
    finally:
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            await conn.execute(
                text("DELETE FROM analyses WHERE id = :analysis_id"),
                {"analysis_id": analysis_id},
            )
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            await conn.execute(
                text("DELETE FROM organizations WHERE id = :org_id"),
                {"org_id": org_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_patent_browser_filters_malformed_reports_before_json_expansion() -> None:  # noqa: E501
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    valid_analysis_id = uuid.uuid4()
    running_analysis_id = uuid.uuid4()
    non_array_patents_id = uuid.uuid4()
    non_array_entries_id = uuid.uuid4()
    missing_span_id = uuid.uuid4()
    reasoning_only_span_id = uuid.uuid4()
    empty_provenance_id = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    valid_patent_id = f"US-VALID-{valid_analysis_id.hex[:8]}"
    running_patent_id = f"US-RUNNING-{running_analysis_id.hex[:8]}"
    non_array_entries_patent_id = f"US-BAD-ENTRIES-{non_array_entries_id.hex[:8]}"
    missing_span_patent_id = f"US-MISSING-SPAN-{missing_span_id.hex[:8]}"
    reasoning_only_patent_id = f"US-REASONING-{reasoning_only_span_id.hex[:8]}"
    empty_provenance_patent_id = f"US-EMPTY-SPANS-{empty_provenance_id.hex[:8]}"

    valid_report = _patent_browser_report(
        patent_id=valid_patent_id,
        title="Valid patent row",
        risk_level="medium",
    )
    running_report = _patent_browser_report(
        patent_id=running_patent_id,
        title="Running report row",
        risk_level="high",
    )
    non_array_patents_report = valid_report_data()
    non_array_patents_report["patent_analyses"] = {"not": "an array"}
    non_array_entries_report = _patent_browser_report(
        patent_id=non_array_entries_patent_id,
        title="Bad entries row",
        risk_level="high",
    )
    non_array_entries_report["claim_source_span_map"]["entries"] = {"not": "an array"}
    missing_span_report = _patent_browser_report(
        patent_id=missing_span_patent_id,
        title="Missing span row",
        risk_level="high",
    )
    missing_span_report["claim_source_span_map"]["entries"][0]["source_span_ids"] = [
        "span-does-not-exist"
    ]
    reasoning_only_report = _patent_browser_report(
        patent_id=reasoning_only_patent_id,
        title="Reasoning-only span row",
        risk_level="medium",
    )
    reasoning_only_entry = reasoning_only_report["claim_source_span_map"]["entries"][0]
    reasoning_only_entry["source_span_ids"] = ["reasoning-only-span"]
    reasoning_only_report["claim_source_span_map"]["spans"] = {
        "reasoning-only-span": {
            "span_id": "reasoning-only-span",
            "source_type": "claim_reasoning",
            "patent_id": reasoning_only_patent_id,
            "claim_number": reasoning_only_entry["claim_number"],
            "element_number": reasoning_only_entry["element_number"],
            "citation": "",
            "excerpt": "Generated reasoning is not evidence-grade source support.",
        }
    }
    empty_provenance_report = valid_report_data(
        patent_analyses=[
            {
                "patent_id": empty_provenance_patent_id,
                "title": "Empty provenance row",
                "assignee": "Praviar Canary",
                "risk_level": "medium",
                "expiry_date": "2035-01-01",
            }
        ],
        claim_source_span_map={
            "generated_from": "postgres_patent_browser_canary",
            "entries": [],
            "spans": {},
            "unsupported_customer_visible_claim_count": 0,
            "needs_review_count": 0,
        },
    )

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES (:org_id, :clerk_org_id, 'Patent Browser Canary Tenant', :slug)
                    """
                ),
                {
                    "org_id": org_id,
                    "clerk_org_id": f"org_{org_id.hex}",
                    "slug": f"patent-browser-canary-{org_id.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, clerk_user_id, org_id, email, full_name, role)
                    VALUES (:user_id, :clerk_user_id, :org_id, 'patent-canary@example.test', 'Patent Canary', 'admin')
                    """
                ),
                {
                    "user_id": user_id,
                    "clerk_user_id": f"user_{user_id.hex}",
                    "org_id": org_id,
                },
            )

        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            for analysis_id, compound_input, status, report_data in (
                (valid_analysis_id, "valid-patent-canary", "completed", valid_report),
                (running_analysis_id, "running-patent-canary", "running", running_report),
                (
                    non_array_patents_id,
                    "non-array-patents-canary",
                    "completed",
                    non_array_patents_report,
                ),
                (
                    non_array_entries_id,
                    "non-array-entries-canary",
                    "completed",
                    non_array_entries_report,
                ),
                (missing_span_id, "missing-span-canary", "completed", missing_span_report),
                (
                    reasoning_only_span_id,
                    "reasoning-only-span-canary",
                    "completed",
                    reasoning_only_report,
                ),
                (
                    empty_provenance_id,
                    "empty-provenance-canary",
                    "completed",
                    empty_provenance_report,
                ),
            ):
                await conn.execute(
                    text(
                        """
                        INSERT INTO analyses (
                            id,
                            org_id,
                            compound_input,
                            initiated_by,
                            report_data,
                            status,
                            completed_at
                        )
                        VALUES (
                            :analysis_id,
                            :org_id,
                            :compound_input,
                            :user_id,
                            CAST(:report_data AS jsonb),
                            :status,
                            CASE
                                WHEN :status = 'completed' THEN clock_timestamp()
                                ELSE NULL
                            END
                        )
                        """
                    ),
                    {
                        "analysis_id": analysis_id,
                        "org_id": org_id,
                        "compound_input": compound_input,
                        "user_id": user_id,
                        "report_data": json.dumps(report_data),
                        "status": status,
                    },
                )

        async with session_factory() as session, session.begin():
            await session.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            patents = await list_patents_for_org(
                session,
                org_id=org_id,
                risk_ratings_restricted=False,
                risk_filter=None,
                page=1,
                per_page=20,
            )
            assert patents["total"] == 1
            assert [item["id"] for item in patents["items"]] == [valid_patent_id]

            detail = await get_patent_detail_for_org(
                session,
                patent_id=valid_patent_id,
                org_id=org_id,
                risk_ratings_restricted=False,
            )
            assert detail["patent_analysis"]["patent_id"] == valid_patent_id

            for blocked_patent_id in (
                running_patent_id,
                non_array_entries_patent_id,
                missing_span_patent_id,
                reasoning_only_patent_id,
                empty_provenance_patent_id,
            ):
                with pytest.raises(APIError) as exc_info:
                    await get_patent_detail_for_org(
                        session,
                        patent_id=blocked_patent_id,
                        org_id=org_id,
                        risk_ratings_restricted=False,
                    )
                assert exc_info.value.status == 404
    finally:
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
            await conn.execute(
                text("DELETE FROM analyses WHERE org_id = :org_id"),
                {"org_id": org_id},
            )
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            await conn.execute(
                text("DELETE FROM organizations WHERE id = :org_id"),
                {"org_id": org_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_org_erasure_rebinds_rls_to_target_org() -> None:
    """execute_org_erasure must rebind RLS to the target org.

    The caller (platform superadmin) has their own org bound in the session.
    Without the explicit rebind in execute_org_erasure, the UPDATE matches zero
    rows because RLS filters by the session's current_org_id, not the target.
    This test verifies the rebind works and does NOT contaminate the caller's
    org data.
    """
    from api.config import get_settings
    from api.services.offboarding import (
        ClaimedUseErasureAuthorization,
        execute_org_erasure,
    )

    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    erasure_engine = create_async_engine(os.environ["GLOBAL_ERASURE_DATABASE_URL"])
    org_target = uuid.uuid4()
    org_superadmin = uuid.uuid4()
    user_target = uuid.uuid4()
    user_superadmin = uuid.uuid4()
    analysis_target = uuid.uuid4()
    analysis_superadmin = uuid.uuid4()
    target_receipt_id = uuid.uuid4()
    erasure_session_factory = async_sessionmaker(
        erasure_engine,
        expire_on_commit=False,
    )

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES
                      (:org_t, :clerk_t, 'Erasure Target Org', :slug_t),
                      (:org_s, :clerk_s, 'SuperAdmin Org', :slug_s)
                    """
                ),
                {
                    "org_t": org_target,
                    "clerk_t": f"org_{org_target.hex}",
                    "slug_t": f"erasure-target-{org_target.hex}",
                    "org_s": org_superadmin,
                    "clerk_s": f"org_{org_superadmin.hex}",
                    "slug_s": f"erasure-superadmin-{org_superadmin.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, clerk_user_id, org_id, email, full_name, role)
                    VALUES
                      (:user_t, :clerk_ut, :org_t, 'target@erasure.test',
                       'Target User', 'attorney'),
                      (:user_s, :clerk_us, :org_s, 'super@erasure.test',
                       'Super Admin', 'admin')
                    """
                ),
                {
                    "user_t": user_target,
                    "clerk_ut": f"user_{user_target.hex}",
                    "org_t": org_target,
                    "user_s": user_superadmin,
                    "clerk_us": f"user_{user_superadmin.hex}",
                    "org_s": org_superadmin,
                },
            )

        for org_id_loop, analysis_id_loop, compound_input, user_id_loop in (
            (org_target, analysis_target, "erasure-target-compound", user_target),
            (org_superadmin, analysis_superadmin, "superadmin-compound", user_superadmin),
        ):
            async with engine.begin() as conn:
                await conn.execute(
                    select(func.set_config("app.current_org_id", str(org_id_loop), True))
                )
                await conn.execute(
                    text(
                        """
                        INSERT INTO analyses
                            (
                                id,
                                org_id,
                                compound_input,
                                initiated_by,
                                status,
                                completed_at
                            )
                        VALUES
                            (
                                :analysis_id,
                                :org_id,
                                :compound,
                                :user_id,
                                'completed',
                                clock_timestamp()
                            )
                        """
                    ),
                    {
                        "analysis_id": analysis_id_loop,
                        "org_id": org_id_loop,
                        "compound": compound_input,
                        "user_id": user_id_loop,
                    },
                )

        target_report_id = f"erasure-report-{analysis_target.hex}"
        target_report_fingerprint = analysis_target.hex * 2
        target_issued_at = datetime.now(UTC)
        target_receipt_payload = _claimed_use_receipt_payload(
            analysis_id=analysis_target,
            org_id=org_target,
            issuer_user_id=user_target,
            report_id=target_report_id,
            report_fingerprint=target_report_fingerprint,
            issued_at=target_issued_at,
        )
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_target), True)))
            await conn.execute(
                text(
                    """
                    UPDATE analyses
                       SET config = CAST(:config AS jsonb),
                           report_data = CAST(:report_data AS jsonb)
                     WHERE id = :analysis_id
                    """
                ),
                {
                    "analysis_id": analysis_target,
                    "config": json.dumps(
                        {"product_context": {"accused_acts": [{"act": "regulatory_submission"}]}}
                    ),
                    "report_data": json.dumps(
                        {
                            "report_id": target_report_id,
                            "patent_details": {"US1234567B2": {}},
                        }
                    ),
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO analysis_claimed_use_receipts (
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
                        :receipt_id,
                        :analysis_id,
                        :org_id,
                        :report_id,
                        :report_fingerprint,
                        'US1234567B2',
                        1,
                        0,
                        :accused_act_sha256,
                        :receipt_sha256,
                        CAST(:receipt_payload AS jsonb),
                        :issuer_user_id,
                        :issued_at
                    )
                    """
                ),
                {
                    "receipt_id": target_receipt_id,
                    "analysis_id": analysis_target,
                    "org_id": org_target,
                    "report_id": target_report_id,
                    "report_fingerprint": target_report_fingerprint,
                    "accused_act_sha256": "c" * 64,
                    "receipt_sha256": target_receipt_payload["receipt_sha256"],
                    "receipt_payload": json.dumps(target_receipt_payload),
                    "issuer_user_id": user_target,
                    "issued_at": target_issued_at,
                },
            )

        # Only the dedicated erasure identity can cross the legal-ledger
        # boundary. The central object remains target/actor/time bound.
        settings = get_settings().model_copy(update={"platform_admin_user_ids": [user_superadmin]})
        async with erasure_session_factory() as session:
            await session.execute(
                select(func.set_config("app.current_org_id", str(org_superadmin), True))
            )
            with patch(
                "api.services.offboarding.get_settings",
                return_value=settings,
            ):
                result = await execute_org_erasure(
                    session,
                    org_id=org_target,
                    authorization=ClaimedUseErasureAuthorization(
                        authorization_id=uuid.uuid4(),
                        request_id=uuid.uuid4(),
                        org_id=org_target,
                        actor_kind="platform_superadmin",
                        actor_user_id=user_superadmin,
                        actor_email="super@erasure.test",
                        authorized_at=datetime.now(UTC),
                    ),
                    use_database_boundary=True,
                )

        assert result["deletion_status"] == "erased"

        # Target org's analysis must be soft-deleted
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", str(org_target), True)))
            status = (
                await conn.execute(
                    text("SELECT status FROM analyses WHERE id = :analysis_id"),
                    {"analysis_id": analysis_target},
                )
            ).scalar_one_or_none()
            assert status == "deleted", f"expected 'deleted', got {status!r}"
            receipt_count = await conn.scalar(
                text("SELECT count(*) FROM analysis_claimed_use_receipts WHERE id = :receipt_id"),
                {"receipt_id": target_receipt_id},
            )
            assert receipt_count == 0

        # Superadmin org's analysis must be untouched
        async with engine.begin() as conn:
            await conn.execute(
                select(func.set_config("app.current_org_id", str(org_superadmin), True))
            )
            status = (
                await conn.execute(
                    text("SELECT status FROM analyses WHERE id = :analysis_id"),
                    {"analysis_id": analysis_superadmin},
                )
            ).scalar_one_or_none()
            assert status == "completed", f"superadmin analysis contaminated: got {status!r}"

    finally:
        await engine.dispose()
        await erasure_engine.dispose()


@pytest.mark.asyncio
async def test_postgres_stripe_nil_uuid_sentinel_satisfies_fk_and_rls() -> None:
    """Nil-UUID sentinel row must satisfy stripe_events FK and RLS.

    stripe_events.org_id is ForeignKey(organizations.id). The webhook handler
    inserts org_id=uuid.UUID(int=0) for unresolved orgs and binds
    app.current_org_id to the same nil UUID to pass the RLS WITH CHECK.

    This verifies:
    1. The sentinel organizations row (id=nil UUID) exists after migration
       i3d4e5f6a7b8.
    2. INSERT into stripe_events with org_id=nil UUID succeeds — FK satisfied,
       RLS WITH CHECK satisfied.
    3. The row is visible under the nil-UUID RLS context.
    """
    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    nil_uuid = "00000000-0000-0000-0000-000000000000"
    engine = create_async_engine(database_url)
    sentinel_event_id = f"evt_rls_canary_{uuid.uuid4().hex}"

    try:
        # 1. Sentinel org row must exist from migration i3d4e5f6a7b8
        async with engine.begin() as conn:
            sentinel_clerk_org = (
                await conn.execute(
                    text("SELECT clerk_org_id FROM organizations WHERE id = :nil_uuid"),
                    {"nil_uuid": nil_uuid},
                )
            ).scalar_one_or_none()
            assert sentinel_clerk_org == "__stripe_receipt_sentinel__", (
                f"Sentinel org row missing or wrong clerk_org_id: {sentinel_clerk_org!r}"
            )

        # 2. INSERT succeeds under nil-UUID RLS context
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", nil_uuid, True)))
            await conn.execute(
                text(
                    """
                    INSERT INTO stripe_events
                        (id, stripe_event_id, event_type, org_id, processed)
                    VALUES
                        (gen_random_uuid(), :event_id,
                         'checkout.session.completed', CAST(:nil_uuid AS uuid), false)
                    """
                ),
                {"event_id": sentinel_event_id, "nil_uuid": nil_uuid},
            )

        # 3. Row is visible under nil-UUID context
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", nil_uuid, True)))
            event_type = (
                await conn.execute(
                    text("SELECT event_type FROM stripe_events WHERE stripe_event_id = :event_id"),
                    {"event_id": sentinel_event_id},
                )
            ).scalar_one_or_none()
            assert event_type == "checkout.session.completed"

    finally:
        async with engine.begin() as conn:
            await conn.execute(select(func.set_config("app.current_org_id", nil_uuid, True)))
            await conn.execute(
                text("DELETE FROM stripe_events WHERE stripe_event_id = :event_id"),
                {"event_id": sentinel_event_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_load_due_monitor_refs_respects_non_bypassrls_role() -> None:
    """A tenant role must not read scheduled monitors across organizations.

    The monitors table has FORCE ROW LEVEL SECURITY with an org_isolation
    policy. Scheduled dispatch separately fails closed unless its worker role
    has BYPASSRLS. This canary intentionally uses the NOBYPASSRLS application
    role and proves that no-context reads return nothing while an explicit org
    context sees only that organization's monitor.
    """
    from api.services.monitor_runtime import load_due_monitor_refs

    database_url = os.environ["DATABASE_URL"]
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail("RLS canaries require a real asyncpg PostgreSQL DATABASE_URL")

    engine = create_async_engine(database_url)
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    monitor_a = uuid.uuid4()
    monitor_b = uuid.uuid4()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO organizations (id, clerk_org_id, name, slug)
                    VALUES
                      (:org_a, :clerk_a, 'Monitor Canary Org A', :slug_a),
                      (:org_b, :clerk_b, 'Monitor Canary Org B', :slug_b)
                    """
                ),
                {
                    "org_a": org_a,
                    "clerk_a": f"org_{org_a.hex}",
                    "slug_a": f"monitor-canary-a-{org_a.hex}",
                    "org_b": org_b,
                    "clerk_b": f"org_{org_b.hex}",
                    "slug_b": f"monitor-canary-b-{org_b.hex}",
                },
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO users (id, clerk_user_id, org_id, email, full_name, role)
                    VALUES
                      (:user_a, :clerk_ua, :org_a, 'monitor-a@canary.test', 'Monitor A', 'admin'),
                      (:user_b, :clerk_ub, :org_b, 'monitor-b@canary.test', 'Monitor B', 'admin')
                    """
                ),
                {
                    "user_a": user_a,
                    "clerk_ua": f"user_{user_a.hex}",
                    "org_a": org_a,
                    "user_b": user_b,
                    "clerk_ub": f"user_{user_b.hex}",
                    "org_b": org_b,
                },
            )

        for org_id, user_id, monitor_id in (
            (org_a, user_a, monitor_a),
            (org_b, user_b, monitor_b),
        ):
            async with engine.begin() as conn:
                await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
                await conn.execute(
                    text(
                        """
                        INSERT INTO monitors (
                            id, org_id, user_id,
                            compound_smiles, compound_name,
                            schedule, is_active,
                            jurisdiction_bundle, target_jurisdictions,
                            strategy_version, monitoring_strategy,
                            watch_targets, last_run_mode, last_run_status,
                            last_run_summary, last_patent_count,
                            cached_patent_ids, last_snapshot
                        ) VALUES (
                            :monitor_id, :org_id, :user_id,
                            'C', 'Canary Compound',
                            'weekly', true,
                            'custom', '[]'::jsonb,
                            '2026-04-monitor-v1', '{}'::jsonb,
                            '[]'::jsonb, '', '',
                            '', 0,
                            '[]'::jsonb, '{}'::jsonb
                        )
                        """
                    ),
                    {
                        "monitor_id": monitor_id,
                        "org_id": org_id,
                        "user_id": user_id,
                    },
                )

        async with session_factory() as session, session.begin():
            due_refs = await load_due_monitor_refs(session)
            assert due_refs == []

        for org_id, expected_monitor_id in (
            (org_a, monitor_a),
            (org_b, monitor_b),
        ):
            async with session_factory() as session, session.begin():
                await session.execute(
                    select(func.set_config("app.current_org_id", str(org_id), True))
                )
                due_refs = await load_due_monitor_refs(session)
            assert due_refs == [(expected_monitor_id, org_id)]

    finally:
        for org_id, monitor_id in ((org_a, monitor_a), (org_b, monitor_b)):
            async with engine.begin() as conn:
                await conn.execute(select(func.set_config("app.current_org_id", str(org_id), True)))
                await conn.execute(
                    text("DELETE FROM monitors WHERE id = :monitor_id"),
                    {"monitor_id": monitor_id},
                )
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM users WHERE id IN (:user_a, :user_b)"),
                {"user_a": user_a, "user_b": user_b},
            )
            await conn.execute(
                text("DELETE FROM organizations WHERE id IN (:org_a, :org_b)"),
                {"org_a": org_a, "org_b": org_b},
            )
        await engine.dispose()

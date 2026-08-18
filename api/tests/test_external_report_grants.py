"""Hostile tests for recipient-bound external report grants."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import valid_report_data_for_patents
from fastapi import Request, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from api.db.models import ReviewStatus
from api.errors import APIError
from api.external_report_delivery_keyring import ExternalReportDeliveryKeyRing
from api.ratelimit import public_share_challenge_rate_limit_key
from api.schemas.external_sharing import ExternalSharingPolicy
from api.schemas.reports_fto_io import (
    ExternalGrantVerificationResponse,
    ExternalReportGrantCreatedResponse,
)
from api.services import external_report_grants as grants
from api.services.email_models import DeliveryLookupResult, DeliverySubmissionResult
from api.services.public_reports import build_shared_report_payload

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
VALID_TOKEN = "T" * 43
VALID_ACCESS_SECRET = "A" * 43


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return SimpleNamespace(all=lambda: self.value or [])

    def all(self):
        return self.value or []


class _Session:
    def __init__(self, result=None):
        self.execute = AsyncMock(return_value=_Result(result))
        self.commit = AsyncMock()
        self.flush = AsyncMock()
        self.rollback = AsyncMock()
        self.add = MagicMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _grant(**overrides):
    values = {
        "id": uuid.uuid4(),
        "org_id": uuid.uuid4(),
        "analysis_id": uuid.uuid4(),
        "created_by": uuid.uuid4(),
        "recipient_email": "counsel@example.com",
        "recipient_email_normalized": "counsel@example.com",
        "recipient_domain": "example.com",
        "grant_token_hash": grants._secret_digest(VALID_TOKEN),
        "report_fingerprint": "report-fingerprint",
        "delivery_operation_key_digest": "d" * 64,
        "delivery_request_hash": "r" * 64,
        "delivery_encryption_key_id": "dev-v1",
        "delivery_state": "active",
        "delivery_token_ciphertext": None,
        "delivery_dispatch_started_at": None,
        "delivery_provider_accepted_at": None,
        "delivery_terminal_at": None,
        "delivery_terminal_reason": None,
        "delivery_provider_message_id": None,
        "delivery_reconciliation_alerted_at": None,
        "delivery_reconciliation_attempt_count": 0,
        "delivery_reconciliation_next_attempt_at": None,
        "invitation_sent_at": NOW - timedelta(minutes=5),
        "verification_code_hash": None,
        "verification_expires_at": None,
        "verification_sent_at": None,
        "verification_consumed_at": None,
        "verification_attempt_count": 0,
        "access_secret_hash": None,
        "access_expires_at": None,
        "expires_at": NOW + timedelta(days=7),
        "revoked_at": None,
        "max_views": 25,
        "view_count": 0,
        "download_allowed": False,
        "max_downloads": 0,
        "download_count": 0,
        "last_accessed_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _needs_review_report_data() -> dict:
    """Return the claim-support state emitted by the real pipeline."""
    report = valid_report_data_for_patents([])
    report.update(
        {
            "report_id": "report-1",
            "trust_mode": "counsel",
            "opinion_readiness": {
                "trust_mode": "counsel",
                "export_ready": True,
                "jurisdictions_blocking_export": [],
            },
            "patent_analyses": [],
            "claim_source_span_map": {
                "generated_from": "pipeline_claim_analysis",
                "entries": [
                    {
                        "assertion_id": "assertion-needs-review-1",
                        "patent_id": "US91000017A1",
                        "claim_number": 1,
                        "element_number": 2,
                        "report_section": "claim_element_analysis",
                        "assertion_text": "Claim 1 element 2 was assessed as unclear.",
                        "source_span_ids": [],
                        "support_status": "needs_review",
                        "customer_visible": True,
                        "review_required": True,
                    }
                ],
                "spans": {},
                "unsupported_customer_visible_claim_count": 0,
                "needs_review_count": 1,
            },
        }
    )
    return report


def _claim_reviewer_decision(*, report_fingerprint: str) -> SimpleNamespace:
    return SimpleNamespace(
        finding_type="claim_element",
        finding_ref="assertion-needs-review-1",
        report_fingerprint=report_fingerprint,
        decision="accept",
        reviewer_user_id="clerk_reviewer_1",
    )


@pytest.mark.parametrize(
    "token",
    ["short", "x" * 65, "x" * 39, "x" * 42 + "/"],
)
def test_grant_locator_rejects_malformed_tokens_before_database_access(token: str) -> None:
    with pytest.raises(APIError) as exc_info:
        grants.validate_grant_token_shape(token)

    assert exc_info.value.status == 404


def test_challenge_rate_limit_is_token_wide_without_raw_locator() -> None:
    def request_for(client_ip: str) -> Request:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": f"/share/{VALID_TOKEN}/challenge",
                "path_params": {"token": VALID_TOKEN},
                "query_string": b"",
                "headers": [],
                "client": (client_ip, 443),
            }
        )
        return request

    first_key = public_share_challenge_rate_limit_key(request_for("203.0.113.1"))
    second_key = public_share_challenge_rate_limit_key(request_for("198.51.100.2"))

    assert first_key == second_key
    assert first_key.startswith("public-share-challenge:")
    assert VALID_TOKEN not in first_key


@pytest.mark.parametrize("secret", ["short", "x" * 65, "x" * 42 + "/"])
def test_access_proof_response_schema_rejects_malformed_service_output(
    secret: str,
) -> None:
    with pytest.raises(ValidationError):
        ExternalGrantVerificationResponse(
            access_secret=secret,
            access_expires_at=NOW + timedelta(minutes=30),
        )


def test_create_response_schema_rejects_malformed_grant_locator() -> None:
    with pytest.raises(ValidationError):
        ExternalReportGrantCreatedResponse(
            id=uuid.uuid4(),
            recipient_email="counsel@example.com",
            recipient_domain="example.com",
            invitation_sent_at=NOW,
            expires_at=NOW + timedelta(days=7),
            max_views=25,
            view_count=0,
            download_allowed=False,
            max_downloads=0,
            download_count=0,
            last_accessed_at=None,
            status="active",
            share_token="not-url/safe" + "x" * 32,
            invitation_status="provider_accepted",
        )


def test_recipient_normalization_rejects_smtputf8_and_normalizes_domain() -> None:
    assert grants.normalize_recipient_email("Counsel@Example.COM") == (
        "Counsel@example.com",
        "counsel@example.com",
        "example.com",
    )
    with pytest.raises(APIError) as exc_info:
        grants.normalize_recipient_email("δοκιμή@example.com")
    assert exc_info.value.status == 422
    assert grants.normalize_recipient_email("Counsel@BÜCHER.Example") == (
        "Counsel@xn--bcher-kva.example",
        "counsel@xn--bcher-kva.example",
        "xn--bcher-kva.example",
    )


@pytest.mark.parametrize(
    ("overrides", "expected_status"),
    [
        ({"revoked_at": NOW}, 410),
        ({"expires_at": NOW}, 410),
        ({"view_count": 25, "max_views": 25}, 410),
        ({"invitation_sent_at": None}, 410),
        ({"delivery_state": "provider_accepted"}, 410),
        ({"delivery_state": "outcome_unknown"}, 410),
        ({"delivery_state": "rejected"}, 410),
        ({"delivery_state": "cancelled"}, 410),
    ],
)
def test_revoked_expired_exhausted_or_unsent_grants_fail_closed(
    overrides: dict,
    expected_status: int,
) -> None:
    with pytest.raises(APIError) as exc_info:
        grants._ensure_grant_active(_grant(**overrides), now=NOW)
    assert exc_info.value.status == expected_status


@pytest.mark.asyncio
async def test_create_persists_only_digest_and_keeps_existing_access_until_delivery() -> None:
    db = _Session()
    analysis = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        report_data={"report_id": "report-1"},
    )
    creator = uuid.uuid4()
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(
                return_value=ExternalSharingPolicy(
                    mode="open",
                    approved_domains=[],
                )
            ),
        ),
        patch.object(grants, "get_analysis_for_org", AsyncMock(return_value=analysis)),
        patch.object(grants, "ensure_analysis_export_ready", AsyncMock()),
        patch.object(grants.secrets, "token_urlsafe", return_value=VALID_TOKEN),
    ):
        created = await grants.create_external_report_grant(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            created_by=creator,
            recipient_email="Counsel@Example.COM",
            expires_in_days=7,
            max_views=12,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
            now_fn=lambda _timezone: NOW,
        )

    assert created.raw_token == VALID_TOKEN
    assert created.grant.grant_token_hash == grants._secret_digest(VALID_TOKEN)
    assert created.grant.grant_token_hash != VALID_TOKEN
    assert "grant_token" not in created.grant.__dict__
    assert VALID_TOKEN not in created.grant.__dict__.values()
    assert created.grant.download_allowed is False
    assert created.grant.max_downloads == 0
    assert created.grant.invitation_sent_at is None
    assert db.execute.await_count == 3
    assert created.grant.delivery_state == "prepared"
    assert created.grant.delivery_token_ciphertext
    assert VALID_TOKEN not in created.grant.delivery_token_ciphertext
    assert created.grant.recipient_email == "Counsel@example.com"
    assert created.grant.recipient_email_normalized == "counsel@example.com"


@pytest.mark.asyncio
async def test_same_idempotency_key_replays_exact_request_without_second_grant() -> None:
    org_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    request_hash = grants._delivery_request_hash(
        analysis_id=analysis_id,
        recipient_email="counsel@example.com",
        expires_in_days=7,
        max_views=12,
    )
    existing = _grant(
        org_id=org_id,
        analysis_id=analysis_id,
        delivery_state="prepared",
        delivery_request_hash=request_hash,
        delivery_token_ciphertext="encrypted-token",
        invitation_sent_at=None,
    )
    db = _Session(result=existing)
    with (
        patch.object(grants, "_delivery_operation_digest", return_value="d" * 64),
        patch.object(grants, "_decrypt_delivery_token", return_value=VALID_TOKEN) as decrypt,
        patch.object(grants, "get_external_sharing_policy", AsyncMock()) as policy,
    ):
        replay = await grants.create_external_report_grant(
            db,
            analysis_id=analysis_id,
            org_id=org_id,
            created_by=uuid.uuid4(),
            recipient_email="counsel@example.com",
            expires_in_days=7,
            max_views=12,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
            now_fn=lambda _timezone: NOW,
        )

    assert replay.is_replay is True
    assert replay.grant is existing
    assert replay.raw_token == VALID_TOKEN
    decrypt.assert_called_once_with(existing)
    policy.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_same_idempotency_key_with_different_body_is_conflict() -> None:
    existing = _grant(
        delivery_state="prepared",
        delivery_request_hash="0" * 64,
        invitation_sent_at=None,
    )
    db = _Session(result=existing)
    with (
        patch.object(grants, "_delivery_operation_digest", return_value="d" * 64),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.create_external_report_grant(
            db,
            analysis_id=existing.analysis_id,
            org_id=existing.org_id,
            created_by=uuid.uuid4(),
            recipient_email="different@example.com",
            expires_in_days=30,
            max_views=3,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
        )

    assert exc_info.value.status == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_expired_same_key_replay_never_dispatches_stale_invitation() -> None:
    analysis_id = uuid.uuid4()
    existing = _grant(
        analysis_id=analysis_id,
        delivery_state="prepared",
        invitation_sent_at=None,
        expires_at=NOW - timedelta(seconds=1),
        delivery_token_ciphertext="encrypted-token",
        delivery_request_hash=grants._delivery_request_hash(
            analysis_id=analysis_id,
            recipient_email="counsel@example.com",
            expires_in_days=7,
            max_views=12,
        ),
    )
    db = _Session(result=existing)
    with (
        patch.object(grants, "_delivery_operation_digest", return_value="d" * 64),
        patch.object(grants, "_decrypt_delivery_token") as decrypt,
        pytest.raises(APIError) as exc_info,
    ):
        await grants.create_external_report_grant(
            db,
            analysis_id=existing.analysis_id,
            org_id=existing.org_id,
            created_by=uuid.uuid4(),
            recipient_email=existing.recipient_email_normalized,
            expires_in_days=7,
            max_views=12,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 410
    decrypt.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_claim_rechecks_expiry_before_revealing_token() -> None:
    grant = _grant(
        delivery_state="prepared",
        invitation_sent_at=None,
        expires_at=NOW,
        delivery_token_ciphertext="encrypted-token",
    )
    db = _Session(result=grant)
    with (
        patch.object(grants, "_decrypt_delivery_token") as decrypt,
        pytest.raises(APIError) as exc_info,
    ):
        await grants.claim_external_report_delivery_dispatch(
            db,
            grant_id=grant.id,
            analysis_id=grant.analysis_id,
            org_id=grant.org_id,
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 410
    decrypt.assert_not_called()


def test_delivery_operation_digest_is_tenant_scoped() -> None:
    key = "delivery-operation-123"  # gitleaks:allow
    first = grants._delivery_operation_digest(org_id=uuid.uuid4(), idempotency_key=key)
    second = grants._delivery_operation_digest(org_id=uuid.uuid4(), idempotency_key=key)

    assert first != second
    assert len(first) == len(second) == 64


def test_delivery_key_rotation_retains_old_ciphertext_and_stable_operation_digest() -> None:
    old_ring = ExternalReportDeliveryKeyRing(
        active_key_id="v1",
        encryption_keys={"v1": b"A" * 32},
        operation_hmac_key=b"H" * 32,
    )
    rotated_ring = ExternalReportDeliveryKeyRing(
        active_key_id="v2",
        encryption_keys={"v1": b"A" * 32, "v2": b"B" * 32},
        operation_hmac_key=b"H" * 32,
    )
    grant = _grant(delivery_encryption_key_id=None)
    with patch.object(grants, "_delivery_keyring", return_value=old_ring):
        first_digest = grants._delivery_operation_digest(
            org_id=grant.org_id,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
        )
        grant.delivery_token_ciphertext = grants._encrypt_delivery_token(
            grant,
            VALID_TOKEN,
        )

    assert grant.delivery_encryption_key_id == "v1"
    with patch.object(grants, "_delivery_keyring", return_value=rotated_ring):
        second_digest = grants._delivery_operation_digest(
            org_id=grant.org_id,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
        )
        decrypted = grants._decrypt_delivery_token(grant)

    assert second_digest == first_digest
    assert decrypted == VALID_TOKEN


def test_delivery_keyring_rejects_noncanonical_or_unknown_material() -> None:
    payload = {
        "schema_version": "praviar.external-report-delivery-keyring.v1",
        "active_key_id": "v1",
        "encryption_keys": {"v1": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE!"},
        "operation_hmac_key": "SEhISEhISEhISEhISEhISEhISEhISEhISEhISEhISEg",
    }
    with pytest.raises(ValueError, match="base64url"):
        ExternalReportDeliveryKeyRing.from_secret(json.dumps(payload))

    payload["encryption_keys"] = {"v1": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE"}
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        ExternalReportDeliveryKeyRing.from_secret(json.dumps(payload))


@pytest.mark.asyncio
async def test_dispatch_boundary_is_persisted_once_and_never_reclaimed() -> None:
    grant = _grant(
        delivery_state="prepared",
        invitation_sent_at=None,
        delivery_token_ciphertext="encrypted-token",
    )
    db = _Session(result=grant)
    with patch.object(grants, "_decrypt_delivery_token", return_value=VALID_TOKEN) as decrypt:
        first = await grants.claim_external_report_delivery_dispatch(
            db,
            grant_id=grant.id,
            analysis_id=grant.analysis_id,
            org_id=grant.org_id,
            now_fn=lambda _timezone: NOW,
        )
        with pytest.raises(APIError) as exc_info:
            await grants.claim_external_report_delivery_dispatch(
                db,
                grant_id=grant.id,
                analysis_id=grant.analysis_id,
                org_id=grant.org_id,
                now_fn=lambda _timezone: NOW,
            )

    assert first.needs_provider_submission is True
    assert grant.delivery_state == "dispatching"
    assert grant.delivery_dispatch_started_at == NOW
    assert exc_info.value.status == 503
    decrypt.assert_called_once_with(grant)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state", ["prepared", "dispatching", "provider_accepted", "outcome_unknown"]
)
async def test_revoking_pending_delivery_cancels_and_erases_ciphertext(state: str) -> None:
    grant = _grant(
        delivery_state=state,
        invitation_sent_at=None,
        delivery_token_ciphertext="encrypted-token",
    )
    analysis = SimpleNamespace(id=grant.analysis_id, org_id=grant.org_id)
    db = _Session(result=grant)
    with (
        patch.object(grants, "get_analysis_for_org", AsyncMock(return_value=analysis)),
        patch.object(grants, "_refresh_analysis_share_state", AsyncMock()),
    ):
        revoked = await grants.revoke_external_report_grant(
            db,
            grant_id=grant.id,
            analysis_id=grant.analysis_id,
            org_id=grant.org_id,
            now_fn=lambda _timezone: NOW,
        )

    assert revoked.delivery_state == "cancelled"
    assert revoked.revoked_at == NOW
    assert revoked.delivery_terminal_at == NOW
    assert revoked.delivery_token_ciphertext is None


@pytest.mark.asyncio
async def test_different_key_cannot_overtake_an_ambiguous_recipient_delivery() -> None:
    unresolved = _grant(
        delivery_state="outcome_unknown",
        invitation_sent_at=None,
        delivery_token_ciphertext=None,
    )
    db = _Session()
    db.execute.side_effect = [_Result(None), _Result(None), _Result([unresolved])]
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(return_value=ExternalSharingPolicy(mode="open", approved_domains=[])),
        ),
        patch.object(grants, "get_analysis_for_org", AsyncMock()) as load_analysis,
        pytest.raises(APIError) as exc_info,
    ):
        await grants.create_external_report_grant(
            db,
            analysis_id=unresolved.analysis_id,
            org_id=unresolved.org_id,
            created_by=uuid.uuid4(),
            recipient_email=unresolved.recipient_email_normalized,
            expires_in_days=7,
            max_views=12,
            idempotency_key="different-delivery-operation-456",
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 409
    assert "outcome_unknown" in exc_info.value.detail
    load_analysis.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_case_variant_mailbox_cannot_create_a_second_unresolved_delivery() -> None:
    unresolved = _grant(
        recipient_email="Counsel@example.com",
        recipient_email_normalized="counsel@example.com",
        delivery_state="dispatching",
        invitation_sent_at=None,
        delivery_token_ciphertext="encrypted-token",
    )
    db = _Session()
    db.execute.side_effect = [_Result(None), _Result(None), _Result([unresolved])]
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(return_value=ExternalSharingPolicy(mode="open", approved_domains=[])),
        ),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.create_external_report_grant(
            db,
            analysis_id=unresolved.analysis_id,
            org_id=unresolved.org_id,
            created_by=uuid.uuid4(),
            recipient_email="counsel@EXAMPLE.COM",
            expires_in_days=7,
            max_views=12,
            idempotency_key="case-variant-operation-456",
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 409


@pytest.mark.asyncio
async def test_same_key_winner_is_rechecked_after_waiting_for_org_lock() -> None:
    analysis_id = uuid.uuid4()
    winner = _grant(
        analysis_id=analysis_id,
        delivery_state="prepared",
        invitation_sent_at=None,
        delivery_token_ciphertext="encrypted-token",
        delivery_request_hash=grants._delivery_request_hash(
            analysis_id=analysis_id,
            recipient_email="counsel@example.com",
            expires_in_days=7,
            max_views=12,
        ),
    )
    db = _Session()
    db.execute.side_effect = [_Result(None), _Result(winner)]
    with (
        patch.object(grants, "_delivery_operation_digest", return_value="d" * 64),
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(return_value=ExternalSharingPolicy(mode="open", approved_domains=[])),
        ),
        patch.object(grants, "_decrypt_delivery_token", return_value=VALID_TOKEN),
    ):
        replay = await grants.create_external_report_grant(
            db,
            analysis_id=analysis_id,
            org_id=winner.org_id,
            created_by=uuid.uuid4(),
            recipient_email="Counsel@example.com",
            expires_in_days=7,
            max_views=12,
            idempotency_key="same-key-concurrent-123",
            now_fn=lambda _timezone: NOW,
        )

    assert replay.is_replay is True
    assert replay.grant is winner
    assert replay.raw_token == VALID_TOKEN
    assert db.execute.await_count == 2


class _IntegrityOriginError(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__(constraint_name)
        self.constraint_name = constraint_name


def test_integrity_constraint_name_reads_asyncpg_chained_origin() -> None:
    adapter_error = RuntimeError("asyncpg adapter")
    adapter_error.__cause__ = _IntegrityOriginError(
        "uq_external_report_grants_org_delivery_operation"
    )
    failure = IntegrityError("insert", {}, adapter_error)

    assert grants._integrity_constraint_name(failure) == (
        "uq_external_report_grants_org_delivery_operation"
    )


@pytest.mark.asyncio
async def test_unrelated_integrity_failure_is_not_retried_or_swallowed() -> None:
    db = _Session()
    failure = IntegrityError(
        "insert",
        {},
        _IntegrityOriginError("fk_external_report_grants_analysis_id"),
    )
    db.flush.side_effect = failure
    analysis = SimpleNamespace(
        id=uuid.uuid4(), org_id=uuid.uuid4(), report_data={"report_id": "report-1"}
    )
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(return_value=ExternalSharingPolicy(mode="open", approved_domains=[])),
        ),
        patch.object(grants, "get_analysis_for_org", AsyncMock(return_value=analysis)),
        patch.object(grants, "ensure_analysis_export_ready", AsyncMock()),
        pytest.raises(IntegrityError) as exc_info,
    ):
        await grants.create_external_report_grant(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            created_by=uuid.uuid4(),
            recipient_email="counsel@example.com",
            expires_in_days=7,
            max_views=12,
            idempotency_key="unrelated-integrity-123",
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value is failure
    assert db.flush.await_count == 1
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_named_operation_unique_failure_recovers_winner_once() -> None:
    analysis = SimpleNamespace(
        id=uuid.uuid4(), org_id=uuid.uuid4(), report_data={"report_id": "report-1"}
    )
    request_hash = grants._delivery_request_hash(
        analysis_id=analysis.id,
        recipient_email="counsel@example.com",
        expires_in_days=7,
        max_views=12,
    )
    winner = _grant(
        org_id=analysis.org_id,
        analysis_id=analysis.id,
        delivery_state="prepared",
        invitation_sent_at=None,
        delivery_token_ciphertext="encrypted-token",
        delivery_request_hash=request_hash,
    )
    db = _Session()
    db.execute.side_effect = [
        _Result(None),
        _Result(None),
        _Result([]),
        _Result(winner),
    ]
    db.flush.side_effect = IntegrityError(
        "insert",
        {},
        _IntegrityOriginError("uq_external_report_grants_org_delivery_operation"),
    )
    with (
        patch.object(grants, "_delivery_operation_digest", return_value="d" * 64),
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(return_value=ExternalSharingPolicy(mode="open", approved_domains=[])),
        ),
        patch.object(grants, "get_analysis_for_org", AsyncMock(return_value=analysis)),
        patch.object(grants, "ensure_analysis_export_ready", AsyncMock()),
        patch.object(grants, "_decrypt_delivery_token", return_value=VALID_TOKEN),
    ):
        replay = await grants.create_external_report_grant(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            created_by=uuid.uuid4(),
            recipient_email="Counsel@example.com",
            expires_in_days=7,
            max_views=12,
            idempotency_key="named-integrity-123",
            now_fn=lambda _timezone: NOW,
        )

    assert replay.grant is winner
    assert replay.is_replay is True
    assert db.flush.await_count == 1
    db.rollback.assert_awaited_once()


def test_expired_prepared_grant_serializes_as_expired_not_pending() -> None:
    grant = _grant(
        delivery_state="prepared",
        invitation_sent_at=None,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert grants.serialize_grant(grant)["status"] == "expired"


@pytest.mark.parametrize(
    ("terminal_reason", "expected_status"),
    [
        ("policy", "delivery_cancelled_by_policy"),
        ("expired", "delivery_cancelled_expired"),
        ("retention_expired", "delivery_cancelled_retention_expired"),
    ],
)
def test_cancelled_delivery_serializes_authoritative_terminal_reason(
    terminal_reason: str,
    expected_status: str,
) -> None:
    grant = _grant(
        delivery_state="cancelled",
        invitation_sent_at=None,
        revoked_at=NOW,
        delivery_terminal_reason=terminal_reason,
    )

    assert grants.serialize_grant(grant)["status"] == expected_status


def test_reconciliation_alert_takes_precedence_over_generic_unknown_status() -> None:
    grant = _grant(
        delivery_state="outcome_unknown",
        invitation_sent_at=None,
        delivery_reconciliation_alerted_at=NOW,
    )

    assert grants.serialize_grant(grant)["status"] == "delivery_reconciliation_alert"


@pytest.mark.asyncio
async def test_reconciliation_cancels_expired_abandoned_prepared_delivery() -> None:
    grant = _grant(
        delivery_state="prepared",
        invitation_sent_at=None,
        expires_at=NOW - timedelta(seconds=1),
        delivery_token_ciphertext="encrypted-token",
    )
    snapshot = SimpleNamespace(
        id=grant.id,
        analysis_id=grant.analysis_id,
        delivery_operation_key_digest=grant.delivery_operation_key_digest,
        recipient_email_normalized=grant.recipient_email_normalized,
        delivery_state=grant.delivery_state,
        delivery_dispatch_started_at=None,
        expires_at=grant.expires_at,
        revoked_at=None,
        delivery_token_ciphertext=grant.delivery_token_ciphertext,
    )
    db = _Session(result=[snapshot])
    provider = SimpleNamespace(lookup_outbound_submission=AsyncMock())
    with patch.object(
        grants,
        "_lock_delivery_reconciliation_candidate",
        AsyncMock(return_value=grant),
    ):
        counts = await grants.reconcile_external_report_deliveries(
            db,
            org_id=grant.org_id,
            email_client=provider,
            now_fn=lambda _timezone: NOW,
        )

    assert grant.delivery_state == "cancelled"
    assert grant.revoked_at == NOW
    assert grant.delivery_terminal_reason == "expired"
    assert grant.delivery_token_ciphertext is None
    assert counts["cancelled_expired"] == 1
    provider.lookup_outbound_submission.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_reconciliation_lease_cannot_lock_or_apply_grant_write() -> None:
    grant = _grant(delivery_state="outcome_unknown", invitation_sent_at=None)
    candidate = grants._DeliveryReconciliationCandidate(
        grant_id=grant.id,
        analysis_id=grant.analysis_id,
        operation_digest=grant.delivery_operation_key_digest,
        delivery_email=grant.recipient_email,
        canonical_email=grant.recipient_email_normalized,
        delivery_state=grant.delivery_state,
        dispatch_started_at=grant.delivery_dispatch_started_at,
        created_at=grant.created_at,
        expires_at=grant.expires_at,
        revoked_at=None,
        has_ciphertext=False,
        reconciliation_attempt_count=0,
        reconciliation_next_attempt_at=None,
    )
    db = _Session(result=None)
    lease_id = uuid.uuid4()

    locked = await grants._lock_delivery_reconciliation_candidate(
        db,
        org_id=grant.org_id,
        candidate=candidate,
        reconciliation_lease_id=lease_id,
    )

    assert locked is None
    assert db.execute.await_count == 1
    statement = db.execute.await_args.args[0]
    rendered = str(statement)
    assert "external_report_delivery_reconciliation_lease_id" in rendered
    assert "external_report_delivery_reconciliation_lease_expires_at" in rendered
    assert lease_id in statement.compile().params.values()


@pytest.mark.asyncio
async def test_reconciliation_terminalizes_unknown_after_lookup_retention() -> None:
    grant = _grant(
        delivery_state="outcome_unknown",
        invitation_sent_at=None,
        delivery_dispatch_started_at=NOW - timedelta(days=8),
        delivery_token_ciphertext=None,
    )
    snapshot = SimpleNamespace(
        id=grant.id,
        analysis_id=grant.analysis_id,
        delivery_operation_key_digest=grant.delivery_operation_key_digest,
        recipient_email_normalized=grant.recipient_email_normalized,
        delivery_state=grant.delivery_state,
        delivery_dispatch_started_at=grant.delivery_dispatch_started_at,
        expires_at=grant.expires_at,
        revoked_at=None,
        delivery_token_ciphertext=None,
    )
    db = _Session(result=[snapshot])
    provider = SimpleNamespace(lookup_outbound_submission=AsyncMock())
    with (
        patch.object(
            grants,
            "get_settings",
            return_value=SimpleNamespace(postmark_outbound_retention_days=7),
        ),
        patch.object(
            grants,
            "_lock_delivery_reconciliation_candidate",
            AsyncMock(return_value=grant),
        ),
    ):
        counts = await grants.reconcile_external_report_deliveries(
            db,
            org_id=grant.org_id,
            email_client=provider,
            now_fn=lambda _timezone: NOW,
        )

    assert grant.delivery_state == "cancelled"
    assert grant.revoked_at == NOW
    assert grant.delivery_terminal_reason == "retention_expired"
    assert counts["cancelled_expired"] == 1
    assert db.add.call_args.args[0].action == ("report.share.delivery_cancelled_retention_expired")
    provider.lookup_outbound_submission.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery_state", ["dispatching", "outcome_unknown"])
async def test_reconciliation_cancels_expired_unresolved_without_provider_lookup(
    delivery_state: str,
) -> None:
    grant = _grant(
        delivery_state=delivery_state,
        invitation_sent_at=None,
        delivery_dispatch_started_at=NOW - timedelta(minutes=20),
        delivery_token_ciphertext=("encrypted-token" if delivery_state == "dispatching" else None),
        expires_at=NOW - timedelta(seconds=1),
    )
    snapshot = SimpleNamespace(
        id=grant.id,
        analysis_id=grant.analysis_id,
        delivery_operation_key_digest=grant.delivery_operation_key_digest,
        recipient_email=grant.recipient_email,
        recipient_email_normalized=grant.recipient_email_normalized,
        delivery_state=grant.delivery_state,
        delivery_dispatch_started_at=grant.delivery_dispatch_started_at,
        created_at=grant.created_at,
        expires_at=grant.expires_at,
        revoked_at=None,
        delivery_token_ciphertext=grant.delivery_token_ciphertext,
        delivery_reconciliation_attempt_count=0,
        delivery_reconciliation_next_attempt_at=None,
    )
    db = _Session(result=[snapshot])
    provider = SimpleNamespace(lookup_outbound_submission=AsyncMock())
    with patch.object(
        grants,
        "_lock_delivery_reconciliation_candidate",
        AsyncMock(return_value=grant),
    ):
        counts = await grants.reconcile_external_report_deliveries(
            db,
            org_id=grant.org_id,
            email_client=provider,
            now_fn=lambda _timezone: NOW,
        )

    assert grant.delivery_state == "cancelled"
    assert grant.revoked_at == NOW
    assert grant.delivery_token_ciphertext is None
    assert counts["cancelled_expired"] == 1
    provider.lookup_outbound_submission.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciliation_batches_prevent_first_20_from_starving_row_21() -> None:
    org_id = uuid.uuid4()
    all_grants = [
        _grant(
            org_id=org_id,
            delivery_state="outcome_unknown",
            invitation_sent_at=None,
            delivery_dispatch_started_at=NOW - timedelta(hours=1),
            delivery_token_ciphertext=None,
        )
        for _ in range(21)
    ]

    def snapshot(grant):
        return SimpleNamespace(
            id=grant.id,
            analysis_id=grant.analysis_id,
            delivery_operation_key_digest=grant.delivery_operation_key_digest,
            recipient_email=grant.recipient_email,
            recipient_email_normalized=grant.recipient_email_normalized,
            delivery_state=grant.delivery_state,
            delivery_dispatch_started_at=grant.delivery_dispatch_started_at,
            created_at=grant.created_at,
            expires_at=grant.expires_at,
            revoked_at=None,
            delivery_token_ciphertext=None,
            delivery_reconciliation_attempt_count=(grant.delivery_reconciliation_attempt_count),
            delivery_reconciliation_next_attempt_at=(grant.delivery_reconciliation_next_attempt_at),
        )

    provider = SimpleNamespace(
        lookup_outbound_submission=AsyncMock(return_value=DeliveryLookupResult(status="not_found"))
    )
    first_db = _Session(result=[snapshot(grant) for grant in all_grants])
    with patch.object(
        grants,
        "_lock_delivery_reconciliation_candidate",
        AsyncMock(side_effect=all_grants[:20]),
    ):
        first_counts = await grants.reconcile_external_report_deliveries(
            first_db,
            org_id=org_id,
            email_client=provider,
            now_fn=lambda _timezone: NOW,
        )

    assert first_counts["lookup_not_found"] == 20
    assert first_counts["processed"] == 20
    assert first_counts["has_more"] is True
    assert all(
        grant.delivery_reconciliation_attempt_count == 1
        and grant.delivery_reconciliation_next_attempt_at == NOW + timedelta(minutes=5)
        for grant in all_grants[:20]
    )
    first_statement = first_db.execute.await_args.args[0]
    rendered = str(first_statement)
    assert "delivery_reconciliation_next_attempt_at IS NULL" in rendered
    assert "delivery_reconciliation_next_attempt_at <=" in rendered
    assert first_statement._limit_clause.value == 21

    last_grant = all_grants[20]
    second_db = _Session(result=[snapshot(last_grant)])
    with patch.object(
        grants,
        "_lock_delivery_reconciliation_candidate",
        AsyncMock(return_value=last_grant),
    ):
        second_counts = await grants.reconcile_external_report_deliveries(
            second_db,
            org_id=org_id,
            email_client=provider,
            now_fn=lambda _timezone: NOW,
        )

    assert second_counts["lookup_not_found"] == 1
    assert last_grant.delivery_reconciliation_attempt_count == 1
    assert last_grant.delivery_reconciliation_next_attempt_at == NOW + timedelta(minutes=5)
    assert provider.lookup_outbound_submission.await_count == 21


@pytest.mark.asyncio
async def test_reconciliation_commits_snapshot_before_provider_lookup_and_apply_lock() -> None:
    grant = _grant(
        delivery_state="dispatching",
        invitation_sent_at=None,
        delivery_dispatch_started_at=NOW - timedelta(minutes=20),
        delivery_token_ciphertext="encrypted-token",
    )
    snapshot = SimpleNamespace(
        id=grant.id,
        analysis_id=grant.analysis_id,
        delivery_operation_key_digest=grant.delivery_operation_key_digest,
        recipient_email_normalized=grant.recipient_email_normalized,
        delivery_state=grant.delivery_state,
        delivery_dispatch_started_at=grant.delivery_dispatch_started_at,
        expires_at=grant.expires_at,
        revoked_at=None,
        delivery_token_ciphertext=grant.delivery_token_ciphertext,
    )
    db = _Session(result=[snapshot])
    events: list[str] = []

    async def commit() -> None:
        events.append("commit")

    async def lookup(**_kwargs):
        events.append("lookup")
        return DeliveryLookupResult(status="not_found")

    async def lock(*_args, **_kwargs):
        events.append("lock")
        return grant

    db.commit.side_effect = commit
    provider = SimpleNamespace(lookup_outbound_submission=AsyncMock(side_effect=lookup))
    with patch.object(
        grants,
        "_lock_delivery_reconciliation_candidate",
        AsyncMock(side_effect=lock),
    ):
        counts = await grants.reconcile_external_report_deliveries(
            db,
            org_id=grant.org_id,
            email_client=provider,
            now_fn=lambda _timezone: NOW,
        )

    assert events[:3] == ["commit", "lookup", "lock"]
    assert grant.delivery_state == "outcome_unknown"
    assert grant.delivery_token_ciphertext is None
    assert counts["lookup_not_found"] == 1
    assert counts["outcome_unknown"] == 1


@pytest.mark.asyncio
async def test_reconciliation_late_provider_match_activates_without_resubmission() -> None:
    grant = _grant(
        delivery_state="outcome_unknown",
        invitation_sent_at=None,
        delivery_dispatch_started_at=NOW - timedelta(hours=1),
        delivery_token_ciphertext=None,
    )
    snapshot = SimpleNamespace(
        id=grant.id,
        analysis_id=grant.analysis_id,
        delivery_operation_key_digest=grant.delivery_operation_key_digest,
        recipient_email_normalized=grant.recipient_email_normalized,
        delivery_state=grant.delivery_state,
        delivery_dispatch_started_at=grant.delivery_dispatch_started_at,
        expires_at=grant.expires_at,
        revoked_at=None,
        delivery_token_ciphertext=None,
    )
    db = _Session(result=[snapshot])
    provider = SimpleNamespace(
        lookup_outbound_submission=AsyncMock(
            return_value=DeliveryLookupResult(status="found", message_id="postmark-1")
        )
    )
    activate = AsyncMock(return_value="activated")
    with (
        patch.object(
            grants,
            "_lock_delivery_reconciliation_candidate",
            AsyncMock(return_value=grant),
        ),
        patch.object(grants, "_activate_reconciled_delivery", activate),
    ):
        counts = await grants.reconcile_external_report_deliveries(
            db,
            org_id=grant.org_id,
            email_client=provider,
            now_fn=lambda _timezone: NOW,
        )

    assert grant.delivery_state == "provider_accepted"
    assert grant.delivery_provider_message_id == "postmark-1"
    assert counts["activated"] == 1
    provider.lookup_outbound_submission.assert_awaited_once()
    activate.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconciled_acceptance_cancelled_if_policy_tightens() -> None:
    grant = _grant(
        delivery_state="provider_accepted",
        invitation_sent_at=None,
        delivery_token_ciphertext="encrypted-token",
    )
    candidate = grants._DeliveryReconciliationCandidate(
        grant_id=grant.id,
        analysis_id=grant.analysis_id,
        operation_digest=grant.delivery_operation_key_digest,
        delivery_email=grant.recipient_email,
        canonical_email=grant.recipient_email_normalized,
        delivery_state="provider_accepted",
        dispatch_started_at=NOW - timedelta(hours=1),
        created_at=grant.created_at,
        expires_at=grant.expires_at,
        revoked_at=None,
        has_ciphertext=True,
        reconciliation_attempt_count=0,
        reconciliation_next_attempt_at=None,
    )
    db = _Session()
    with (
        patch.object(
            grants,
            "activate_external_report_grant",
            AsyncMock(
                side_effect=APIError(
                    403,
                    "Recipient domain not approved",
                    "Policy tightened",
                )
            ),
        ),
        patch.object(
            grants,
            "_lock_delivery_reconciliation_candidate",
            AsyncMock(return_value=grant),
        ),
    ):
        outcome = await grants._activate_reconciled_delivery(
            db,
            org_id=grant.org_id,
            candidate=candidate,
            now=NOW,
            now_fn=lambda _timezone: NOW,
            reconciliation_lease_id=None,
        )

    assert outcome == "cancelled_by_policy"
    assert grant.delivery_state == "cancelled"
    assert grant.revoked_at == NOW
    assert grant.delivery_token_ciphertext is None
    assert db.add.call_args.args[0].action == "report.share.delivery_cancelled_by_policy"
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_accepted_activation_rotates_only_working_delivered_grants() -> None:
    analysis = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    pending = _grant(
        analysis_id=analysis.id,
        org_id=analysis.org_id,
        recipient_email="Counsel@example.com",
        recipient_email_normalized="counsel@example.com",
        invitation_sent_at=None,
        delivery_state="provider_accepted",
    )
    old = _grant(
        analysis_id=analysis.id,
        org_id=analysis.org_id,
        recipient_email="counsel@example.com",
        recipient_email_normalized=pending.recipient_email_normalized,
        verification_code_hash="old-code",
        verification_expires_at=NOW + timedelta(minutes=5),
        access_secret_hash="old-proof",
        access_expires_at=NOW + timedelta(minutes=20),
    )
    session = _Session()
    session.execute.side_effect = [_Result(pending), _Result([old])]
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(
                return_value=ExternalSharingPolicy(
                    mode="open",
                    approved_domains=[],
                )
            ),
        ) as get_policy,
        patch.object(grants, "get_analysis_for_org", AsyncMock(return_value=analysis)),
        patch.object(grants, "_refresh_analysis_share_state", AsyncMock()) as refresh,
    ):
        activated = await grants.activate_external_report_grant(
            session,
            grant_id=pending.id,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            now_fn=lambda _timezone: NOW,
        )

    assert get_policy.await_args.kwargs["for_update"] is True
    assert pending.invitation_sent_at == NOW
    assert old.revoked_at == NOW
    assert old.verification_code_hash is None
    assert old.verification_expires_at is None
    assert old.access_secret_hash is None
    assert old.access_expires_at is None
    assert pending.recipient_email != old.recipient_email
    assert pending.recipient_email_normalized == old.recipient_email_normalized
    assert activated.rotated_grant_ids == (old.id,)
    rotation_statement = session.execute.await_args_list[1].args[0]
    rendered = str(rotation_statement)
    assert "invitation_sent_at IS NOT NULL" in rendered
    assert "external_report_grants.id !=" in rendered
    refresh.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_policy_tightening_between_create_and_delivery_blocks_activation_without_rotation():
    analysis = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    pending = _grant(
        analysis_id=analysis.id,
        org_id=analysis.org_id,
        invitation_sent_at=None,
        recipient_domain="blocked.example",
    )
    session = _Session(result=pending)
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(
                return_value=ExternalSharingPolicy(
                    mode="approved_domains_only",
                    approved_domains=["approved.example"],
                )
            ),
        ),
        patch.object(grants, "get_analysis_for_org", AsyncMock(return_value=analysis)),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.activate_external_report_grant(
            session,
            grant_id=pending.id,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 403
    assert pending.invitation_sent_at is None
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_create_checks_exact_domain_policy_while_holding_org_lock() -> None:
    analysis = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        report_data={"report_id": "report-1"},
    )
    db = _Session()
    policy = ExternalSharingPolicy(
        mode="approved_domains_only",
        approved_domains=["approved.example"],
    )
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(return_value=policy),
        ) as get_policy,
        patch.object(grants, "get_analysis_for_org", AsyncMock(return_value=analysis)),
        patch.object(grants, "ensure_analysis_export_ready", AsyncMock()),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.create_external_report_grant(
            db,
            analysis_id=analysis.id,
            org_id=analysis.org_id,
            created_by=uuid.uuid4(),
            recipient_email="counsel@sub.approved.example",
            expires_in_days=7,
            max_views=12,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 403
    assert get_policy.await_args.kwargs == {
        "org_id": analysis.org_id,
        "for_update": True,
    }
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_stored_policy_blocks_grant_before_analysis_load() -> None:
    db = _Session()
    analysis_loader = AsyncMock()
    with (
        patch.object(
            grants,
            "get_external_sharing_policy",
            AsyncMock(
                side_effect=APIError(
                    500,
                    "External sharing policy unavailable",
                    "External sharing is blocked",
                )
            ),
        ),
        patch.object(grants, "get_analysis_for_org", analysis_loader),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.create_external_report_grant(
            db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            recipient_email="counsel@example.com",
            expires_in_days=7,
            max_views=12,
            idempotency_key="delivery-operation-123",  # gitleaks:allow
        )

    assert exc_info.value.status == 500
    analysis_loader.assert_not_awaited()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_invitation_provider_rejection_never_activates_grant() -> None:
    grant = _grant(
        recipient_email="Counsel@example.com",
        recipient_email_normalized="counsel@example.com",
        invitation_sent_at=None,
    )
    created = grants.CreatedGrant(grant=grant, raw_token=VALID_TOKEN)
    email_client = SimpleNamespace(
        submit_email_once=AsyncMock(return_value=DeliverySubmissionResult(status="rejected"))
    )
    with (
        patch.object(
            grants,
            "get_settings",
            return_value=SimpleNamespace(app_url="https://app.example.test"),
        ),
    ):
        provider_result = await grants.send_external_report_grant_invitation(
            created,
            email_client=email_client,
        )
    assert provider_result.status == "rejected"
    assert email_client.submit_email_once.await_args.kwargs["to"] == ("Counsel@example.com")
    assert grant.invitation_sent_at is None
    with pytest.raises(APIError) as access_error:
        grants._ensure_grant_active(grant, now=NOW)
    assert access_error.value.status == 410


@pytest.mark.asyncio
async def test_provider_rejection_invalidates_committed_challenge_fail_closed() -> None:
    grant = _grant()
    first_session = _Session()
    cleanup_session = _Session()
    sessions = iter((first_session, cleanup_session))
    email_client = SimpleNamespace(
        send_email=AsyncMock(return_value=SimpleNamespace(success=False))
    )
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.issue_external_grant_challenge(
            VALID_TOKEN,
            async_session_factory_fn=lambda: next(sessions),
            email_client=email_client,
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 503
    first_session.commit.assert_awaited_once()
    cleanup_session.commit.assert_awaited_once()
    assert grant.verification_code_hash is None
    assert grant.verification_expires_at is None
    assert grant.verification_sent_at is None
    assert grant.access_secret_hash is None


@pytest.mark.asyncio
async def test_otp_is_one_time_and_access_secret_is_digest_only() -> None:
    grant = _grant(
        verification_code_hash="argon2id-digest",
        verification_expires_at=NOW + timedelta(minutes=5),
        verification_sent_at=NOW - timedelta(minutes=1),
    )
    session = _Session()
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        patch.object(grants, "verify_password", return_value=True),
        patch.object(grants.secrets, "token_urlsafe", return_value=VALID_ACCESS_SECRET),
    ):
        access_secret, access_expires_at = await grants.verify_external_grant_challenge(
            VALID_TOKEN,
            code="24681357",
            async_session_factory_fn=lambda: session,
            now_fn=lambda _timezone: NOW,
        )

    assert access_secret == VALID_ACCESS_SECRET
    assert access_expires_at == NOW + grants.ACCESS_TTL
    assert grant.access_secret_hash == grants._secret_digest(VALID_ACCESS_SECRET)
    assert grant.access_secret_hash != VALID_ACCESS_SECRET
    assert grant.verification_code_hash is None
    assert grant.verification_consumed_at == NOW
    assert session.add.call_args.args[0].details["recipient_email"] == "counsel@example.com"

    replay_session = _Session()
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        pytest.raises(APIError) as replay_error,
    ):
        await grants.verify_external_grant_challenge(
            VALID_TOKEN,
            code="24681357",
            async_session_factory_fn=lambda: replay_session,
            now_fn=lambda _timezone: NOW,
        )
    assert replay_error.value.status == 401


@pytest.mark.asyncio
async def test_wrong_otp_attempt_is_persisted_and_eighth_attempt_locks_out() -> None:
    grant = _grant(
        verification_code_hash="argon2id-digest",
        verification_expires_at=NOW + timedelta(minutes=5),
        verification_sent_at=NOW - timedelta(minutes=1),
        verification_attempt_count=6,
    )
    session = _Session()
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        patch.object(grants, "verify_password", return_value=False),
        pytest.raises(APIError) as wrong_error,
    ):
        await grants.verify_external_grant_challenge(
            VALID_TOKEN,
            code="00000000",
            async_session_factory_fn=lambda: session,
            now_fn=lambda _timezone: NOW,
        )
    assert wrong_error.value.status == 401
    assert grant.verification_attempt_count == 7
    session.commit.assert_awaited_once()

    grant.verification_attempt_count = grants.MAX_VERIFICATION_ATTEMPTS
    locked_session = _Session()
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        patch.object(grants, "verify_password") as verify_mock,
        pytest.raises(APIError) as locked_error,
    ):
        await grants.verify_external_grant_challenge(
            VALID_TOKEN,
            code="24681357",
            async_session_factory_fn=lambda: locked_session,
            now_fn=lambda _timezone: NOW,
        )
    assert locked_error.value.status == 429
    verify_mock.assert_not_called()
    locked_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sender_list_and_revoke_queries_are_cross_tenant_safe() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    list_session = _Session(result=[])
    with patch.object(grants, "get_analysis_for_org", AsyncMock()):
        assert (
            await grants.list_external_report_grants(
                list_session,
                analysis_id=analysis_id,
                org_id=org_id,
            )
            == []
        )
    list_statement = list_session.execute.await_args.args[0]
    list_sql = str(list_statement)
    assert "external_report_grants.analysis_id" in list_sql
    assert "external_report_grants.org_id" in list_sql
    assert analysis_id in list_statement.compile().params.values()
    assert org_id in list_statement.compile().params.values()

    revoke_session = _Session(result=None)
    with (
        patch.object(grants, "get_analysis_for_org", AsyncMock()),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.revoke_external_report_grant(
            revoke_session,
            grant_id=uuid.uuid4(),
            analysis_id=analysis_id,
            org_id=org_id,
            now_fn=lambda _timezone: NOW,
        )
    assert exc_info.value.status == 404
    revoke_statement = revoke_session.execute.await_args.args[0]
    revoke_sql = str(revoke_statement)
    assert "external_report_grants.id" in revoke_sql
    assert "external_report_grants.analysis_id" in revoke_sql
    assert "external_report_grants.org_id" in revoke_sql


@pytest.mark.asyncio
async def test_wrong_access_secret_fails_before_analysis_lookup() -> None:
    grant = _grant(
        access_secret_hash=grants._secret_digest(VALID_ACCESS_SECRET),
        access_expires_at=NOW + timedelta(minutes=10),
    )
    session = _Session()
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.fetch_authorized_shared_analysis(
            VALID_TOKEN,
            access_secret="B" * 43,
            async_session_factory_fn=lambda: session,
            ip_address="203.0.113.1",
            now_fn=lambda _timezone: NOW,
        )
    assert exc_info.value.status == 401
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_view_is_named_metered_and_watermarked() -> None:
    analysis = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        report_data={"report_id": "report-1"},
        share_view_count=4,
        share_last_viewed_at=None,
    )
    grant = _grant(
        org_id=analysis.org_id,
        analysis_id=analysis.id,
        access_secret_hash=grants._secret_digest(VALID_ACCESS_SECRET),
        access_expires_at=NOW + timedelta(minutes=10),
    )
    session = _Session(result=analysis)
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        patch.object(grants, "load_analysis_review_status", AsyncMock(return_value=None)),
        patch.object(grants, "load_export_reviewer_decisions", AsyncMock(return_value=[])),
        patch.object(grants, "require_completed_report_payload", return_value=analysis.report_data),
        patch.object(grants, "report_payload_fingerprint", return_value="report-fingerprint"),
        patch.object(grants, "build_export_readiness_blockers", return_value=[]),
        patch.object(grants, "_refresh_analysis_share_state", AsyncMock()),
    ):
        returned = await grants.fetch_authorized_shared_analysis(
            VALID_TOKEN,
            access_secret=VALID_ACCESS_SECRET,
            async_session_factory_fn=lambda: session,
            ip_address="203.0.113.1",
            now_fn=lambda _timezone: NOW,
        )

    assert returned is analysis
    assert grant.view_count == 1
    assert analysis.share_view_count == 5
    assert analysis.__dict__["_share_recipient_email"] == "counsel@example.com"
    assert analysis.__dict__["_share_view_number"] == 1
    assert analysis.__dict__["_share_id"] == str(grant.id)
    assert analysis.__dict__["_share_report_fingerprint"] == "report-fingerprint"
    assert analysis.__dict__["_share_review_status"] is None
    audit = session.add.call_args.args[0]
    assert audit.action == "report.share.viewed"
    assert audit.details["recipient_email"] == "counsel@example.com"
    assert audit.details["view_number"] == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_verified_view_accepts_pipeline_needs_review_state_with_current_decision() -> None:
    report_data = _needs_review_report_data()
    report_fingerprint = grants.report_payload_fingerprint(report_data)
    analysis = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        report_data=report_data,
        share_view_count=0,
        share_last_viewed_at=None,
    )
    grant = _grant(
        org_id=analysis.org_id,
        analysis_id=analysis.id,
        access_secret_hash=grants._secret_digest(VALID_ACCESS_SECRET),
        access_expires_at=NOW + timedelta(minutes=10),
        report_fingerprint=report_fingerprint,
    )
    session = _Session(result=analysis)
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        patch.object(
            grants,
            "load_analysis_review_status",
            AsyncMock(return_value=SimpleNamespace(status=ReviewStatus.APPROVED)),
        ),
        patch.object(
            grants,
            "load_export_reviewer_decisions",
            AsyncMock(
                return_value=[_claim_reviewer_decision(report_fingerprint=report_fingerprint)]
            ),
        ),
        patch.object(grants, "require_completed_report_payload", return_value=report_data),
        patch.object(grants, "_refresh_analysis_share_state", AsyncMock()),
    ):
        returned = await grants.fetch_authorized_shared_analysis(
            VALID_TOKEN,
            access_secret=VALID_ACCESS_SECRET,
            async_session_factory_fn=lambda: session,
            ip_address="203.0.113.1",
            now_fn=lambda _timezone: NOW,
        )

    assert returned is analysis
    assert grant.view_count == 1
    assert analysis.share_view_count == 1
    assert analysis.__dict__["_share_review_status"].status == ReviewStatus.APPROVED
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision_fingerprint", [None, "stale-report-fingerprint"])
async def test_verified_view_rejects_missing_or_stale_claim_decision(
    decision_fingerprint: str | None,
) -> None:
    report_data = _needs_review_report_data()
    report_fingerprint = grants.report_payload_fingerprint(report_data)
    analysis = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        report_data=report_data,
        share_view_count=0,
        share_last_viewed_at=None,
    )
    grant = _grant(
        org_id=analysis.org_id,
        analysis_id=analysis.id,
        access_secret_hash=grants._secret_digest(VALID_ACCESS_SECRET),
        access_expires_at=NOW + timedelta(minutes=10),
        report_fingerprint=report_fingerprint,
    )
    decisions = (
        []
        if decision_fingerprint is None
        else [_claim_reviewer_decision(report_fingerprint=decision_fingerprint)]
    )
    session = _Session(result=analysis)
    with (
        patch.object(grants, "_load_public_grant", AsyncMock(return_value=grant)),
        patch.object(grants, "bind_current_org_to_session", AsyncMock()),
        patch.object(
            grants,
            "load_analysis_review_status",
            AsyncMock(return_value=SimpleNamespace(status=ReviewStatus.APPROVED)),
        ),
        patch.object(
            grants,
            "load_export_reviewer_decisions",
            AsyncMock(return_value=decisions),
        ),
        patch.object(grants, "require_completed_report_payload", return_value=report_data),
        patch.object(grants, "_refresh_analysis_share_state", AsyncMock()),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.fetch_authorized_shared_analysis(
            VALID_TOKEN,
            access_secret=VALID_ACCESS_SECRET,
            async_session_factory_fn=lambda: session,
            ip_address="203.0.113.1",
            now_fn=lambda _timezone: NOW,
        )

    assert exc_info.value.status == 410
    assert exc_info.value.detail == "Shared report is unavailable"
    assert grant.view_count == 0
    assert analysis.share_view_count == 0
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


def test_public_payload_refuses_anonymous_render() -> None:
    analysis = SimpleNamespace(
        status="completed",
        report_data={"report_id": "report-1"},
    )
    with (
        patch(
            "api.services.public_reports.require_completed_report_payload",
            return_value={},
        ),
        patch(
            "api.services.public_reports.build_governed_report_summary",
            return_value={
                "overall_risk": "low",
                "blocking_patents_count": 0,
                "total_patents_found": 0,
                "executive_summary": "Summary",
            },
        ),
        pytest.raises(RuntimeError, match="attribution is missing"),
    ):
        build_shared_report_payload(analysis)


def test_public_payload_binds_safe_report_and_grant_provenance() -> None:
    analysis = SimpleNamespace(
        id=uuid.uuid4(),
        compound_name="Aspirin",
        status="completed",
        updated_at=NOW,
        report_data={
            "report_id": "report-123",
            "generated_at": NOW.isoformat(),
            "source_snapshot_at": (NOW - timedelta(days=1)).isoformat(),
            "praviar_pipeline_version": "2.4.0",
            "llm_models_used": {
                "critic": "claude-critic-2026-07",
                "report": "claude-report-2026-07",
            },
        },
    )
    analysis.__dict__.update(
        {
            "_share_expires_at": NOW + timedelta(days=7),
            "_share_recipient_email": "counsel@example.com",
            "_share_view_number": 2,
            "_share_access_expires_at": NOW + timedelta(minutes=30),
            "_share_id": "grant-123",
            "_share_report_fingerprint": "f" * 64,
            "_share_review_status": SimpleNamespace(status=ReviewStatus.APPROVED),
        }
    )
    with (
        patch(
            "api.services.public_reports.require_completed_report_payload",
            return_value=analysis.report_data,
        ),
        patch(
            "api.services.public_reports.build_governed_report_summary",
            return_value={
                "overall_risk": "low",
                "blocking_patents_count": 0,
                "total_patents_found": 0,
                "executive_summary": "Summary",
            },
        ),
    ):
        payload = build_shared_report_payload(analysis)

    assert payload["report_id"] == "report-123"
    assert payload["share_id"] == "grant-123"
    assert payload["packet_version"] == "recipient-bound-share-v2"
    assert payload["source_snapshot_at"] == (NOW - timedelta(days=1)).isoformat()
    assert payload["pipeline_version"] == "2.4.0"
    assert payload["model_version"] == ("claude-critic-2026-07, claude-report-2026-07")
    assert payload["integrity_digest"] == "f" * 64
    assert payload["review_status"] == "approved"


@pytest.mark.asyncio
async def test_public_route_rejects_query_string_secrets_before_fetch() -> None:
    from api.routes import public

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/share/{VALID_TOKEN}",
            "query_string": b"access_secret=leaked",
            "headers": [],
            "client": ("203.0.113.1", 443),
        }
    )
    response = Response()
    with (
        patch.object(public.limiter, "enabled", False),
        patch.object(public, "fetch_authorized_shared_analysis", AsyncMock()) as fetch_mock,
        pytest.raises(APIError) as exc_info,
    ):
        await public.get_shared_report(VALID_TOKEN, request, response)
    assert exc_info.value.status == 400
    fetch_mock.assert_not_awaited()


def test_migration_revokes_bearer_columns_and_enforces_exact_hash_rls() -> None:
    migration = Path(
        "alembic/versions/y9z0a1b2c3d4_add_recipient_bound_report_grants.py"
    ).read_text(encoding="utf-8")
    assert 'op.drop_column("analyses", "share_token")' in migration
    assert 'op.drop_column("analyses", "share_password_hash")' in migration
    assert "ALTER TABLE external_report_grants FORCE ROW LEVEL SECURITY" in migration
    assert "grant_token_hash = current_setting('app.public_share_grant_hash', true)" in migration
    assert "org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid" in migration


def test_delivery_migration_enforces_one_unresolved_recipient_operation() -> None:
    migration = Path(
        "alembic/versions/c2d3e4f5a6b7_add_durable_external_report_delivery.py"
    ).read_text(encoding="utf-8")

    assert "uq_external_report_grants_one_unresolved_delivery" in migration
    assert '["org_id", "analysis_id", "recipient_email_normalized"]' in migration
    assert "'prepared', 'dispatching'" in migration
    assert "'provider_accepted', 'outcome_unknown'" in migration
    assert "unique=True" in migration
    assert migration.index("SET recipient_email_normalized = lower") < migration.index(
        '"uq_external_report_grants_one_unresolved_delivery"'
    )
    assert "ck_external_report_grants_delivery_activation" in migration
    assert "ck_external_report_grants_unresolved_not_revoked" in migration
    assert "ck_external_report_grants_cancelled_revoked" in migration
    assert "ck_external_report_grants_terminal_ciphertext_cleared" in migration
    assert "ck_external_report_grants_prepared_has_ciphertext" in migration
    assert "cannot downgrade with unresolved external report deliveries" in migration
    no_force = "ALTER TABLE external_report_grants NO FORCE ROW LEVEL SECURITY"
    force = "ALTER TABLE external_report_grants FORCE ROW LEVEL SECURITY"
    assert migration.index(no_force) < migration.index("UPDATE external_report_grants")
    downgrade_source = migration[migration.index("def downgrade()") :]
    assert downgrade_source.index(no_force) < downgrade_source.index("IF EXISTS")
    assert downgrade_source.rindex(force) > downgrade_source.index("IF EXISTS")
    assert "delivery_terminal_reason" in migration
    assert "external_report_delivery_reconciliation_lease_id" in migration


@pytest.mark.asyncio
async def test_sender_routes_create_list_and_revoke_named_grants(attorney_client) -> None:
    client, db = attorney_client
    analysis_id = uuid.uuid4()
    pending = _grant(
        id=uuid.uuid4(),
        analysis_id=analysis_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        invitation_sent_at=None,
        delivery_state="dispatching",
    )
    grant = _grant(
        id=pending.id,
        analysis_id=analysis_id,
        expires_at=pending.expires_at,
        invitation_sent_at=datetime.now(UTC),
        delivery_state="active",
    )
    rotated_grant_id = uuid.uuid4()
    created = grants.CreatedGrant(grant=pending, raw_token=VALID_TOKEN)
    activated = grants.ActivatedGrant(
        grant=grant,
        rotated_grant_ids=(rotated_grant_id,),
    )
    audit_mock = AsyncMock()
    with (
        patch(
            "api.routes.reports.create_external_report_grant",
            AsyncMock(return_value=created),
        ) as create_mock,
        patch(
            "api.routes.reports.claim_external_report_delivery_dispatch",
            AsyncMock(
                return_value=grants.DeliveryDispatch(
                    grant=pending,
                    raw_token=VALID_TOKEN,
                    needs_provider_submission=True,
                )
            ),
        ),
        patch(
            "api.routes.reports.send_external_report_grant_invitation",
            AsyncMock(
                return_value=DeliverySubmissionResult(status="accepted", message_id="postmark-1")
            ),
        ),
        patch(
            "api.routes.reports.record_external_report_delivery_result",
            AsyncMock(return_value=pending),
        ),
        patch(
            "api.routes.reports.activate_external_report_grant",
            AsyncMock(return_value=activated),
        ),
        patch("api.routes.reports.write_audit_log", audit_mock),
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/share",
            headers={"Idempotency-Key": "delivery-operation-123"},  # gitleaks:allow
            json={
                "recipient_email": "counsel@example.com",
                "expires_in_days": 7,
                "max_views": 10,
            },
        )
    assert response.status_code == 201
    assert response.json()["share_token"] == VALID_TOKEN
    assert response.json()["recipient_email"] == "counsel@example.com"
    assert response.json()["download_allowed"] is False
    assert response.json()["status"] == "active"
    assert response.json()["invitation_status"] == "provider_accepted"
    assert create_mock.await_args.kwargs["org_id"] != uuid.UUID(int=0)
    db.commit.assert_awaited()
    audit_actions = [call.kwargs["action"] for call in audit_mock.await_args_list]
    assert audit_actions == [
        "report.share.grant_created",
        "report.share.delivery_dispatch_started",
        "report.share.delivery_provider_accepted",
        "report.share.invitation_sent",
        "report.share.grant_revoked_by_reissue",
        "report.share.recipient_grants_rotated",
    ]
    per_grant_rotation_details = audit_mock.await_args_list[4].kwargs["details"]
    assert per_grant_rotation_details["external_grant_id"] == str(rotated_grant_id)
    assert per_grant_rotation_details["replacement_external_grant_id"] == str(grant.id)
    rotation_details = audit_mock.await_args_list[5].kwargs["details"]
    assert rotation_details["replacement_external_grant_id"] == str(grant.id)
    assert rotation_details["revoked_external_grant_ids"] == [str(rotated_grant_id)]
    assert rotation_details["revoked_grant_count"] == 1

    with patch(
        "api.routes.reports.list_external_report_grants",
        AsyncMock(return_value=[grant]),
    ) as list_mock:
        listed = await client.get(f"/api/v1/reports/{analysis_id}/share")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["recipient_email"] == "counsel@example.com"
    assert "share_token" not in listed.json()["items"][0]
    assert list_mock.await_args.kwargs["analysis_id"] == analysis_id

    with (
        patch(
            "api.routes.reports.revoke_external_report_grant",
            AsyncMock(return_value=grant),
        ) as revoke_mock,
        patch("api.routes.reports.write_audit_log", AsyncMock()),
    ):
        revoked = await client.delete(f"/api/v1/reports/{analysis_id}/share/{grant.id}")
    assert revoked.status_code == 200
    assert revoked.json() == {"status": "revoked"}
    assert revoke_mock.await_args.kwargs["analysis_id"] == analysis_id
    assert revoke_mock.await_args.kwargs["grant_id"] == grant.id


@pytest.mark.asyncio
async def test_provider_rejection_leaves_old_working_grant_intact_and_no_replacement_audit(
    attorney_client,
) -> None:
    client, db = attorney_client
    analysis_id = uuid.uuid4()
    pending = _grant(
        analysis_id=analysis_id,
        invitation_sent_at=None,
        delivery_state="dispatching",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    old = _grant(
        analysis_id=analysis_id,
        invitation_sent_at=datetime.now(UTC),
        access_secret_hash="still-working",
        access_expires_at=datetime.now(UTC) + timedelta(minutes=20),
    )
    created = grants.CreatedGrant(grant=pending, raw_token=VALID_TOKEN)
    activate = AsyncMock()
    audit = AsyncMock()
    with (
        patch(
            "api.routes.reports.create_external_report_grant",
            AsyncMock(return_value=created),
        ),
        patch(
            "api.routes.reports.claim_external_report_delivery_dispatch",
            AsyncMock(
                return_value=grants.DeliveryDispatch(
                    grant=pending,
                    raw_token=VALID_TOKEN,
                    needs_provider_submission=True,
                )
            ),
        ),
        patch(
            "api.routes.reports.send_external_report_grant_invitation",
            AsyncMock(return_value=DeliverySubmissionResult(status="rejected")),
        ),
        patch(
            "api.routes.reports.record_external_report_delivery_result",
            AsyncMock(return_value=pending),
        ),
        patch(
            "api.routes.reports.activate_external_report_grant",
            activate,
        ),
        patch("api.routes.reports.write_audit_log", audit),
    ):
        response = await client.post(
            f"/api/v1/reports/{analysis_id}/share",
            headers={"Idempotency-Key": "delivery-operation-123"},  # gitleaks:allow
            json={
                "recipient_email": pending.recipient_email_normalized,
                "expires_in_days": 7,
                "max_views": 10,
            },
        )

    assert response.status_code == 503
    activate.assert_not_awaited()
    assert old.revoked_at is None
    assert old.access_secret_hash == "still-working"
    assert [call.kwargs["action"] for call in audit.await_args_list] == [
        "report.share.grant_created",
        "report.share.delivery_dispatch_started",
        "report.share.delivery_rejected",
    ]
    assert db.commit.await_count == 3


@pytest.mark.asyncio
async def test_replacement_audit_failure_rolls_back_activation_transaction(attorney_client) -> None:
    client, db = attorney_client
    analysis_id = uuid.uuid4()
    pending = _grant(
        analysis_id=analysis_id,
        invitation_sent_at=None,
        delivery_state="dispatching",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    rotated_id = uuid.uuid4()
    created = grants.CreatedGrant(grant=pending, raw_token=VALID_TOKEN)
    activated = grants.ActivatedGrant(
        grant=_grant(
            id=pending.id,
            analysis_id=analysis_id,
            invitation_sent_at=datetime.now(UTC),
            expires_at=pending.expires_at,
        ),
        rotated_grant_ids=(rotated_id,),
    )
    audit = AsyncMock(
        side_effect=[
            None,
            None,
            None,
            None,
            RuntimeError("audit unavailable"),
        ]
    )
    with (
        patch(
            "api.routes.reports.create_external_report_grant",
            AsyncMock(return_value=created),
        ),
        patch(
            "api.routes.reports.claim_external_report_delivery_dispatch",
            AsyncMock(
                return_value=grants.DeliveryDispatch(
                    grant=pending,
                    raw_token=VALID_TOKEN,
                    needs_provider_submission=True,
                )
            ),
        ),
        patch(
            "api.routes.reports.send_external_report_grant_invitation",
            AsyncMock(
                return_value=DeliverySubmissionResult(status="accepted", message_id="postmark-1")
            ),
        ),
        patch(
            "api.routes.reports.record_external_report_delivery_result",
            AsyncMock(return_value=pending),
        ),
        patch(
            "api.routes.reports.activate_external_report_grant",
            AsyncMock(return_value=activated),
        ),
        patch("api.routes.reports.write_audit_log", audit),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await client.post(
            f"/api/v1/reports/{analysis_id}/share",
            headers={"Idempotency-Key": "delivery-operation-123"},  # gitleaks:allow
            json={
                "recipient_email": pending.recipient_email_normalized,
                "expires_in_days": 7,
                "max_views": 10,
            },
        )

    assert db.commit.await_count == 3
    db.rollback.assert_awaited_once()
    assert [call.kwargs["action"] for call in audit.await_args_list] == [
        "report.share.grant_created",
        "report.share.delivery_dispatch_started",
        "report.share.delivery_provider_accepted",
        "report.share.invitation_sent",
        "report.share.grant_revoked_by_reissue",
    ]


@pytest.mark.asyncio
async def test_grant_activity_is_scoped_and_omits_secrets_and_ip_addresses() -> None:
    grant = _grant()
    invitation_event = SimpleNamespace(
        id=uuid.uuid4(),
        action="report.share.invitation_sent",
        details={
            "external_grant_id": str(grant.id),
            "recipient_email": grant.recipient_email_normalized,
            "provider_message_id": "must-not-be-serialized",
        },
        created_at=NOW,
        ip_address="203.0.113.99",
    )
    view_event = SimpleNamespace(
        id=uuid.uuid4(),
        action="report.share.viewed",
        details={
            "external_grant_id": str(grant.id),
            "view_number": 3,
            "access_secret": "must-not-be-serialized",
        },
        created_at=NOW + timedelta(minutes=1),
        ip_address="198.51.100.12",
    )
    session = _Session()
    session.execute.side_effect = [
        _Result(grant.id),
        _Result([invitation_event, view_event]),
    ]
    with patch.object(grants, "get_analysis_for_org", AsyncMock()):
        items = await grants.list_external_report_grant_activity(
            session,
            grant_id=grant.id,
            analysis_id=grant.analysis_id,
            org_id=grant.org_id,
        )

    assert [item.event for item in items] == ["invitation_sent", "report_viewed"]
    assert items[1].view_number == 3
    serialized = [item.model_dump(mode="json") for item in items]
    assert "ip_address" not in serialized[0]
    assert "recipient_email" not in serialized[0]
    assert "provider_message_id" not in serialized[0]
    assert "access_secret" not in serialized[1]
    audit_statement = session.execute.await_args_list[1].args[0]
    rendered = str(audit_statement)
    assert "audit_logs.org_id" in rendered
    assert "audit_logs.analysis_id" in rendered
    assert "external_grant_id" in audit_statement.compile().params.values()


@pytest.mark.asyncio
async def test_rotated_old_grant_has_an_exact_sender_visible_revocation_event() -> None:
    grant = _grant()
    rotation_event = SimpleNamespace(
        id=uuid.uuid4(),
        action="report.share.grant_revoked_by_reissue",
        details={
            "external_grant_id": str(grant.id),
            "replacement_external_grant_id": str(uuid.uuid4()),
        },
        created_at=NOW,
        ip_address="",
    )
    session = _Session()
    session.execute.side_effect = [
        _Result(grant.id),
        _Result([rotation_event]),
    ]
    with patch.object(grants, "get_analysis_for_org", AsyncMock()):
        items = await grants.list_external_report_grant_activity(
            session,
            grant_id=grant.id,
            analysis_id=grant.analysis_id,
            org_id=grant.org_id,
        )

    assert [item.event for item in items] == ["revoked_by_reissue"]
    assert "replacement_external_grant_id" not in items[0].model_dump()


@pytest.mark.asyncio
async def test_policy_revocation_has_an_exact_sender_visible_activity_event() -> None:
    grant = _grant()
    policy_event = SimpleNamespace(
        id=uuid.uuid4(),
        action="report.share.grant_revoked_by_policy",
        details={
            "external_grant_id": str(grant.id),
            "recipient_domain": grant.recipient_domain,
            "policy_mode": "approved_domains_only",
        },
        created_at=NOW,
        ip_address="",
    )
    session = _Session()
    session.execute.side_effect = [
        _Result(grant.id),
        _Result([policy_event]),
    ]
    with patch.object(grants, "get_analysis_for_org", AsyncMock()):
        items = await grants.list_external_report_grant_activity(
            session,
            grant_id=grant.id,
            analysis_id=grant.analysis_id,
            org_id=grant.org_id,
        )

    assert [item.event for item in items] == ["revoked_by_policy"]
    assert "policy_mode" not in items[0].model_dump()


@pytest.mark.asyncio
async def test_grant_activity_cross_tenant_or_wrong_analysis_returns_not_found() -> None:
    session = _Session(result=None)
    with (
        patch.object(grants, "get_analysis_for_org", AsyncMock()),
        pytest.raises(APIError) as exc_info,
    ):
        await grants.list_external_report_grant_activity(
            session,
            grant_id=uuid.uuid4(),
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_grant_activity_route_is_report_share_role_and_scope_bound(attorney_client) -> None:
    client, _db = attorney_client
    analysis_id = uuid.uuid4()
    grant_id = uuid.uuid4()
    item = {
        "id": uuid.uuid4(),
        "event": "report_viewed",
        "occurred_at": NOW,
        "view_number": 2,
    }
    with patch(
        "api.routes.reports.list_external_report_grant_activity",
        AsyncMock(return_value=[item]),
    ) as activity_mock:
        response = await client.get(f"/api/v1/reports/{analysis_id}/share/{grant_id}/activity")

    assert response.status_code == 200
    assert response.json()["items"][0]["event"] == "report_viewed"
    assert response.json()["items"][0]["view_number"] == 2
    assert activity_mock.await_args.args[0] is _db
    assert activity_mock.await_args.kwargs["grant_id"] == grant_id
    assert activity_mock.await_args.kwargs["analysis_id"] == analysis_id
    assert activity_mock.await_args.kwargs["org_id"] != uuid.UUID(int=0)


@pytest.mark.asyncio
async def test_public_routes_challenge_verify_and_fetch_without_identity_leak(
    public_client,
) -> None:
    access_expires_at = NOW + timedelta(minutes=30)
    attributed_payload = {
        "compound_name": "Aspirin",
        "report_id": "report-123",
        "share_id": "grant-123",
        "packet_version": "recipient-bound-share-v2",
        "source_snapshot_at": NOW.isoformat(),
        "pipeline_version": "2.4.0",
        "model_version": "claude-report-2026-07",
        "integrity_digest": "f" * 64,
        "overall_risk": "medium",
        "blocking_patents_count": 1,
        "total_patents_found": 5,
        "executive_summary": "Review required.",
        "key_findings": [],
        "generated_at": NOW.isoformat(),
        "share_expires_at": (NOW + timedelta(days=7)).isoformat(),
        "verified_recipient_email": "counsel@example.com",
        "attributable_view_number": 2,
        "verified_session_expires_at": access_expires_at.isoformat(),
    }
    with patch(
        "api.routes.public.issue_external_grant_challenge",
        AsyncMock(),
    ):
        challenge = await public_client.post(f"/share/{VALID_TOKEN}/challenge")
    assert challenge.status_code == 200
    assert challenge.json() == {"status": "verification_sent"}
    assert "recipient" not in challenge.text.casefold()
    assert "@" not in challenge.text

    with patch(
        "api.routes.public.verify_external_grant_challenge",
        AsyncMock(return_value=(VALID_ACCESS_SECRET, access_expires_at)),
    ):
        verified = await public_client.post(
            f"/share/{VALID_TOKEN}/verify",
            json={"code": "24681357"},
        )
    assert verified.status_code == 200
    assert verified.json()["access_secret"] == VALID_ACCESS_SECRET

    analysis = SimpleNamespace(id=uuid.uuid4(), org_id=uuid.uuid4())
    with (
        patch(
            "api.routes.public.fetch_authorized_shared_analysis",
            AsyncMock(return_value=analysis),
        ) as fetch_mock,
        patch(
            "api.routes.public.build_shared_report_payload",
            return_value=attributed_payload,
        ),
    ):
        report = await public_client.get(
            f"/share/{VALID_TOKEN}",
            headers={grants.ACCESS_SECRET_HEADER: VALID_ACCESS_SECRET},
        )
    assert report.status_code == 200
    assert report.json()["verified_recipient_email"] == "counsel@example.com"
    assert report.json()["attributable_view_number"] == 2
    assert fetch_mock.await_args.kwargs["access_secret"] == VALID_ACCESS_SECRET
    assert report.headers["cache-control"] == "no-store"

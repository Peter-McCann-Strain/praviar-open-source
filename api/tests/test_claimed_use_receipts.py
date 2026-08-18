"""Adversarial tests for the governed claimed-use counsel receipt workflow."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_analysis_mock, make_mock_db, make_user, valid_report_data_for_patents
from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)
from praviar_pipeline.clients.primary_legal_status import (
    build_primary_legal_status_receipt,
)

from api.db.models import AnalysisClaimedUseReceipt, AnalysisStatus, UserRole
from api.errors import APIError
from api.schemas.claimed_use_receipts import ClaimedUseReceiptIssueRequest
from api.services.claimed_use_receipts import (
    _serialize_row,
    issue_claimed_use_receipt,
    list_claimed_use_receipts,
    revoke_claimed_use_receipt,
)
from api.services.report_access import report_payload_fingerprint

_PATENT_ID = "US12345678A1"
_CLAIMS_TEXT = f"1. Evidence-grade claim span for {_PATENT_ID}."


def _primary_artifact(spec: dict[str, object]) -> bytes:
    payload: dict[str, object] = {
        "schema_version": "primary-legal-status-canonical-artifact-v1",
        "source": spec["source"],
        "evidence_scope": spec["evidence_scope"],
        "source_record_identifier": spec["source_record_identifier"],
        "source_record_patent_number": _PATENT_ID,
        "application_number": ("16123456" if spec["source"] == "uspto_odp_application" else ""),
        "target_jurisdiction": "",
        "raw_status": spec["raw_status"],
    }
    for field in (
        "term_end_date",
        "term_basis_document_ids",
        "effective_claim_ids",
        "current_claim_text_sha256",
        "controlling_claim_document_ids",
    ):
        if field in spec:
            value = spec[field]
            payload[field] = value.isoformat() if isinstance(value, date) else value
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _primary_receipts() -> list[dict]:
    keyring = CheckpointIntegrityKeyRing.from_secret(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
    specs: list[dict[str, object]] = [
        {
            "source": "uspto_odp_application",
            "evidence_scope": "application_prosecution",
            "collection_mode": "api",
            "source_url": "https://api.uspto.gov/api/v1/patent/applications/16123456",
            "source_record_identifier": "16123456",
            "raw_status": "Patented Case",
            "normalized_outcome": "patented",
            "parser_identity": "uspto-odp-application-v1",
        },
        {
            "source": "uspto_odp_application",
            "evidence_scope": "patent_term",
            "collection_mode": "api",
            "source_url": ("https://api.uspto.gov/api/v1/patent/applications/16123456/adjustment"),
            "source_record_identifier": "16123456",
            "raw_status": "Current term",
            "normalized_outcome": "term_current",
            "parser_identity": "uspto-odp-application-v1",
            "term_end_date": date.today() + timedelta(days=3650),
            "term_basis_document_ids": [f"{_PATENT_ID}:grant-and-adjustment"],
        },
        {
            "source": "uspto_maintenance_storefront",
            "evidence_scope": "patent_maintenance",
            "collection_mode": "supervised_manual",
            "source_url": "https://fees.uspto.gov/MaintenanceFees",
            "source_record_identifier": f"{_PATENT_ID}:maintenance",
            "raw_status": "Maintenance fee paid",
            "normalized_outcome": "paid",
            "parser_identity": "supervised-uspto-maintenance-v1",
        },
        {
            "source": "uspto_odp_ptab",
            "evidence_scope": "post_grant_proceeding",
            "collection_mode": "api",
            "source_url": "https://api.uspto.gov/api/v1/patent/trials/proceedings/search",
            "source_record_identifier": f"{_PATENT_ID}:ptab",
            "raw_status": "No proceeding found",
            "normalized_outcome": "none_found",
            "parser_identity": "uspto-odp-ptab-v1",
        },
        {
            "source": "uspto_odp_application",
            "evidence_scope": "current_claim_set",
            "collection_mode": "api",
            "source_url": ("https://api.uspto.gov/api/v1/patent/applications/16123456/documents"),
            "source_record_identifier": "16123456",
            "raw_status": "Current issued claims verified",
            "normalized_outcome": "claims_current",
            "parser_identity": "uspto-odp-application-v1",
            "effective_claim_ids": ["1"],
            "current_claim_text_sha256": hashlib.sha256(_CLAIMS_TEXT.encode()).hexdigest(),
            "controlling_claim_document_ids": [f"{_PATENT_ID}:grant-claims"],
        },
    ]
    return [
        build_primary_legal_status_receipt(
            patent_id=_PATENT_ID,
            collected_at=datetime.now(UTC),
            artifact=_primary_artifact(spec),
            artifact_media_type="application/json",
            limitations=["Exact official-record fixture."],
            attestation_key_id=keyring.active_key_id,
            attestation_key=keyring.active_key(),
            parser_result="conclusive",
            **spec,
        ).model_dump(mode="json")
        for spec in specs
    ]


def _regulatory_act(*, carve_out: str = "partial") -> dict[str, object]:
    return {
        "act": "regulatory_submission",
        "jurisdiction": "US",
        "start_date": (date.today() + timedelta(days=180)).isoformat(),
        "actor": "Example Pharma Inc.",
        "status": "planned",
        "purpose": "regulatory_approval",
        "regulatory_path": "anda",
        "instrumentality": "Proposed aspirin tablet ANDA",
        "liability_theory": "artificial_infringement",
        "target_product_identity": "Aspirin 81 mg oral tablet",
        "proposed_indication": "Secondary prevention of cardiovascular events",
        "proposed_label_use": "One 81 mg tablet administered orally once daily.",
        "label_carve_out_state": carve_out,
    }


def _analysis(
    *,
    analysis_id: uuid.UUID | None = None,
    receipts: list[dict] | None = None,
    carve_out: str = "partial",
):
    report = valid_report_data_for_patents(
        [
            {
                "patent_id": _PATENT_ID,
                "claims_analyzed": [
                    {
                        "claim_number": 1,
                        "claim_type": "independent",
                        "elements": [],
                        "overall_status": "partially_met",
                        "overall_confidence": 0.7,
                        "reasoning": "Method-of-use review required.",
                    }
                ],
            }
        ]
    )
    patent_detail = report["patent_details"].setdefault(_PATENT_ID, {})
    patent_detail.update(
        {
            "patent_id": _PATENT_ID,
            "claims_text": _CLAIMS_TEXT,
            "primary_legal_status_receipts": (
                _primary_receipts() if receipts is None else receipts
            ),
        }
    )
    return make_analysis_mock(
        id=analysis_id or uuid.uuid4(),
        status=AnalysisStatus.COMPLETED,
        report_data=report,
        config={"product_context": {"accused_acts": [_regulatory_act(carve_out=carve_out)]}},
    )


def _issue_body(analysis) -> dict[str, object]:
    return {
        "expected_report_id": analysis.report_data["report_id"],
        "expected_report_fingerprint": report_payload_fingerprint(analysis.report_data),
        "patent_id": _PATENT_ID,
        "claim_number": 1,
        "accused_act_index": 0,
        "claimed_use_match": True,
        "product_identity_match": True,
    }


@pytest.mark.asyncio
async def test_attorney_issues_receipt_bound_to_current_report_and_use(
    attorney_client,
) -> None:
    client, db = attorney_client
    analysis = _analysis()
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(side_effect=[analysis_result, duplicate_result])

    with patch(
        "api.services.claimed_use_receipts.invalidate_approved_review_status_for_decision_change",
        new=AsyncMock(return_value=False),
    ):
        response = await client.post(
            f"/api/v1/analyses/{analysis.id}/claimed-use-receipts",
            json=_issue_body(analysis),
        )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["governs_current_report"] is True
    assert payload["patent_id"] == _PATENT_ID
    assert payload["receipt"]["schema_version"] == "claimed-use-match-v3"
    assert payload["receipt"]["analysis_id"] == str(analysis.id)
    assert payload["receipt"]["org_id"] == str(analysis.org_id)
    assert payload["receipt"]["report_id"] == analysis.report_data["report_id"]
    assert payload["receipt"]["accused_act_index"] == 0
    assert payload["receipt"]["reviewer_role"] == "attorney"
    assert payload["receipt"]["attestation_statement_version"] == (
        "claimed-use-counsel-affirmation-v1"
    )
    assert (
        "primary-legal-status-receipt:sha256:" + payload["receipt"]["current_claim_receipt_sha256"]
    ) in payload["receipt"]["evidence_references"]
    assert (
        f"controlling-claim-document:{_PATENT_ID}:grant-claims"
        in payload["receipt"]["evidence_references"]
    )
    assert payload["receipt"]["current_claim_receipt_sha256"]
    assert payload["receipt"]["controlling_claim_document_ids"] == [f"{_PATENT_ID}:grant-claims"]
    rows = [call.args[0] for call in db.add.call_args_list]
    receipt_row = next(row for row in rows if isinstance(row, AnalysisClaimedUseReceipt))
    assert receipt_row.report_id == analysis.report_data["report_id"]
    assert receipt_row.report_fingerprint == report_payload_fingerprint(analysis.report_data)
    assert len(receipt_row.accused_act_sha256) == 64
    audit = next(row for row in rows if type(row).__name__ == "AuditLog")
    assert audit.action == "claimed_use_receipt.issue"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_stored_receipt_with_recomputed_digest_but_invalid_hmac_fails_closed(
    attorney_client,
) -> None:
    client, db = attorney_client
    analysis = _analysis()
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(side_effect=[analysis_result, duplicate_result])

    with patch(
        "api.services.claimed_use_receipts.invalidate_approved_review_status_for_decision_change",
        new=AsyncMock(return_value=False),
    ):
        response = await client.post(
            f"/api/v1/analyses/{analysis.id}/claimed-use-receipts",
            json=_issue_body(analysis),
        )
    assert response.status_code == 201, response.text
    row = next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], AnalysisClaimedUseReceipt)
    )
    payload = dict(row.receipt_payload)
    payload["attestation_hmac_sha256"] = "f" * 64
    canonical = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    recomputed_digest = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    payload["receipt_sha256"] = recomputed_digest
    row.receipt_payload = payload
    row.receipt_sha256 = recomputed_digest

    with pytest.raises(APIError, match="invalid server attestation"):
        _serialize_row(
            row,
            current_report_id=analysis.report_data["report_id"],
            current_report_fingerprint=report_payload_fingerprint(analysis.report_data),
            current_accused_act_sha256=row.accused_act_sha256,
            user=make_user(role=UserRole.ATTORNEY),
        )


@pytest.mark.asyncio
async def test_issue_rejects_stale_report_fingerprint_before_persistence(
    attorney_client,
) -> None:
    client, db = attorney_client
    analysis = _analysis()
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute = AsyncMock(return_value=result)
    body = _issue_body(analysis)
    body["expected_report_fingerprint"] = "f" * 64

    response = await client.post(
        f"/api/v1/analyses/{analysis.id}/claimed-use-receipts",
        json=body,
    )

    assert response.status_code == 409
    assert "report changed" in response.json()["detail"].lower()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_issue_rejects_missing_primary_status_scope(
    attorney_client,
) -> None:
    client, db = attorney_client
    receipts = [
        receipt
        for receipt in _primary_receipts()
        if receipt["evidence_scope"] != "current_claim_set"
    ]
    analysis = _analysis(receipts=receipts)
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute = AsyncMock(return_value=result)

    response = await client.post(
        f"/api/v1/analyses/{analysis.id}/claimed-use-receipts",
        json=_issue_body(analysis),
    )

    assert response.status_code == 409
    assert "current_claim_set" in response.json()["detail"]
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_issue_rejects_complete_label_carve_out(attorney_client) -> None:
    client, db = attorney_client
    analysis = _analysis(carve_out="complete")
    result = MagicMock()
    result.scalar_one_or_none.return_value = analysis
    db.execute = AsyncMock(return_value=result)

    response = await client.post(
        f"/api/v1/analyses/{analysis.id}/claimed-use-receipts",
        json=_issue_body(analysis),
    )

    assert response.status_code == 422
    assert "complete label carve-out" in response.json()["detail"]
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_list_exposes_only_use_records_the_server_can_attest() -> None:
    db = make_mock_db()
    user = make_user(role=UserRole.ATTORNEY)
    analysis = _analysis()
    analysis.config["product_context"]["accused_acts"].extend(
        [
            {
                **_regulatory_act(),
                "jurisdiction": "EP",
            },
            {
                **_regulatory_act(),
                "status": "hypothetical",
            },
            _regulatory_act(carve_out="complete"),
        ]
    )
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(side_effect=[analysis_result, rows_result])

    response = await list_claimed_use_receipts(
        db,
        analysis_id=analysis.id,
        user=user,
    )

    assert [use.accused_act_index for use in response.eligible_uses] == [0]


@pytest.mark.asyncio
async def test_changed_proposed_use_cannot_leave_receipt_marked_current() -> None:
    db = make_mock_db()
    user = make_user(role=UserRole.ATTORNEY)
    analysis = _analysis()
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(side_effect=[analysis_result, duplicate_result])

    with patch(
        "api.services.claimed_use_receipts.invalidate_approved_review_status_for_decision_change",
        new=AsyncMock(return_value=False),
    ):
        await issue_claimed_use_receipt(
            db,
            analysis_id=analysis.id,
            user=user,
            body=ClaimedUseReceiptIssueRequest.model_validate(_issue_body(analysis)),
        )
    row = next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], AnalysisClaimedUseReceipt)
    )
    analysis.config["product_context"]["accused_acts"][0]["proposed_label_use"] = (
        "A materially changed proposed label use."
    )
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [row]
    db.execute = AsyncMock(side_effect=[analysis_result, rows_result])

    response = await list_claimed_use_receipts(
        db,
        analysis_id=analysis.id,
        user=user,
    )

    assert response.items[0].governs_current_report is False


@pytest.mark.asyncio
async def test_scientist_cannot_read_or_issue_claimed_use_receipts(
    scientist_client,
) -> None:
    client, db = scientist_client
    analysis_id = uuid.uuid4()
    read_response = await client.get(f"/api/v1/analyses/{analysis_id}/claimed-use-receipts")
    issue_response = await client.post(
        f"/api/v1/analyses/{analysis_id}/claimed-use-receipts",
        json={
            "expected_report_id": "report-1",
            "expected_report_fingerprint": "a" * 64,
            "patent_id": _PATENT_ID,
            "claim_number": 1,
            "accused_act_index": 0,
            "claimed_use_match": True,
            "product_identity_match": True,
        },
    )
    assert read_response.status_code == 403
    assert issue_response.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_can_inspect_but_cannot_issue_attorney_affirmation(
    admin_client,
) -> None:
    client, db = admin_client
    analysis_id = uuid.uuid4()

    response = await client.post(
        f"/api/v1/analyses/{analysis_id}/claimed-use-receipts",
        json={
            "expected_report_id": "report-1",
            "expected_report_fingerprint": "a" * 64,
            "patent_id": _PATENT_ID,
            "claim_number": 1,
            "accused_act_index": 0,
            "claimed_use_match": True,
            "product_identity_match": True,
        },
    )

    assert response.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_issuing_attorney_can_revoke_prior_report_without_deleting_payload() -> None:
    db = make_mock_db()
    user = make_user(role=UserRole.ATTORNEY)
    analysis = _analysis()
    body = ClaimedUseReceiptIssueRequest.model_validate(_issue_body(analysis))
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(side_effect=[analysis_result, duplicate_result])

    with patch(
        "api.services.claimed_use_receipts.invalidate_approved_review_status_for_decision_change",
        new=AsyncMock(return_value=False),
    ):
        issued = await issue_claimed_use_receipt(
            db,
            analysis_id=analysis.id,
            user=user,
            body=body,
        )
    receipt_row = next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], AnalysisClaimedUseReceipt)
    )
    original_payload = dict(receipt_row.receipt_payload)
    db.reset_mock()
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    receipt_result = MagicMock()
    receipt_result.scalar_one_or_none.return_value = receipt_row
    db.execute = AsyncMock(side_effect=[analysis_result, receipt_result])
    analysis.status = AnalysisStatus.FAILED

    with patch(
        "api.services.claimed_use_receipts.invalidate_approved_review_status_for_decision_change",
        new=AsyncMock(return_value=False),
    ):
        revoked = await revoke_claimed_use_receipt(
            db,
            analysis_id=analysis.id,
            receipt_id=issued.id,
            user=user,
            reason="The proposed label changed after regulatory review.",
        )

    assert revoked.revoked_at is not None
    assert revoked.governs_current_report is False
    assert receipt_row.receipt_payload == original_payload
    assert receipt_row.revocation_reason == ("The proposed label changed after regulatory review.")
    db.delete.assert_not_awaited()
    audit = next(
        call.args[0] for call in db.add.call_args_list if type(call.args[0]).__name__ == "AuditLog"
    )
    assert audit.action == "claimed_use_receipt.revoke"


@pytest.mark.asyncio
async def test_different_attorney_cannot_revoke_issuer_receipt() -> None:
    db = make_mock_db()
    analysis = _analysis()
    issuer = make_user(role=UserRole.ATTORNEY)
    other_attorney = make_user(role=UserRole.ATTORNEY)
    row = AnalysisClaimedUseReceipt(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        org_id=issuer.org_id,
        report_id=analysis.report_data["report_id"],
        report_fingerprint=report_payload_fingerprint(analysis.report_data),
        patent_id=_PATENT_ID,
        claim_number=1,
        accused_act_index=0,
        accused_act_sha256="a" * 64,
        receipt_sha256="b" * 64,
        receipt_payload={},
        issuer_user_id=issuer.id,
        issued_at=datetime.now(UTC),
    )
    analysis_result = MagicMock()
    analysis_result.scalar_one_or_none.return_value = analysis
    receipt_result = MagicMock()
    receipt_result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(side_effect=[analysis_result, receipt_result])

    with pytest.raises(APIError, match="issuing attorney"):
        await revoke_claimed_use_receipt(
            db,
            analysis_id=analysis.id,
            receipt_id=row.id,
            user=other_attorney,
            reason="The proposed label changed after regulatory review.",
        )
    db.commit.assert_not_awaited()

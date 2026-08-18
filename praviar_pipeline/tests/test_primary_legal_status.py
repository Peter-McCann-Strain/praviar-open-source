from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from praviar_pipeline.clients.primary_legal_status import (
    NationalRegisterAuthority,
    PrimaryLegalStatusReceipt,
    PrimaryLegalStatusRequirement,
    SupervisedMaintenanceImport,
    build_primary_legal_status_receipt,
    evaluate_primary_legal_status_coverage,
    issue_supervised_uspto_maintenance_receipt,
    issue_uspto_odp_patent_term_receipt,
    issue_uspto_odp_ptab_status_receipt,
    primary_legal_status_setup_readiness,
    resolve_report_bound_primary_legal_status_receipts,
    verify_primary_legal_status_receipt,
    verify_primary_legal_status_receipt_digest,
)
from praviar_pipeline.models.patent import PatentHit
from praviar_pipeline.pipeline.search import enrichment

_KEY = b"fixture-primary-authority-key-material-v1"
_NOW = datetime(2026, 7, 26, 12, tzinfo=UTC)
_LIMITATIONS = ["Application status does not itself establish issued-claim enforceability."]


def _official_odp_application_artifact(
    *,
    application_number: str = "16123456",
    patent_number: str = "US1234567",
    raw_status: str = "Patented Case",
) -> bytes:
    return json.dumps(
        {
            "applicationNumberText": application_number,
            "applicationMetaData": {
                "patentNumber": patent_number,
                "applicationStatusDescriptionText": raw_status,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _term_application_record() -> dict[str, object]:
    return {
        "applicationNumberText": "16123456",
        "applicationMetaData": {
            "patentNumber": "1234567",
            "applicationStatusDescriptionText": "Patented Case",
            "applicationTypeCode": "UTL",
            "filingDate": "2010-01-01",
            "grantDate": "2015-01-01",
            "patentTermExtensionDays": 0,
            "inventorBag": [],
        },
        "assignmentBag": [],
    }


def _term_adjustment_response() -> dict[str, object]:
    return {
        "count": 1,
        "patentFileWrapperDataBag": [
            {
                "applicationNumberText": "16123456",
                "patentTermAdjustmentData": {
                    "adjustmentTotalQuantity": 10,
                },
            }
        ],
    }


def _term_continuity_response() -> dict[str, object]:
    return {
        "applicationNumberText": "16123456",
        "parentContinuityBag": [],
        "childContinuityBag": [],
    }


def _term_documents_response() -> dict[str, object]:
    return {
        "applicationNumberText": "16123456",
        "count": 0,
        "results": [],
    }


def test_primary_us_setup_readiness_withholds_incomplete_authority_scopes() -> None:
    class _SigningKeys:
        active_key_id = "current"

        @staticmethod
        def active_key() -> bytes:
            return _KEY

    readiness = primary_legal_status_setup_readiness(
        SimpleNamespace(
            uspto_odp_api_key="configured",
            checkpoint_integrity_keys=_SigningKeys(),
        )
    )

    assert readiness.ready is False
    assert readiness.available_scopes == ["application_prosecution"]
    assert set(readiness.blocked_scopes) == {
        "patent_term",
        "patent_maintenance",
        "post_grant_proceeding",
        "current_claim_set",
    }
    assert any("patent-term-extension" in reason for reason in readiness.failure_reasons)
    assert any("controlling text" in reason for reason in readiness.failure_reasons)


def _canonical_artifact(
    *,
    source: str,
    evidence_scope: str,
    source_record_identifier: str,
    patent_id: str,
    raw_status: str,
    application_number: str = "",
    target_jurisdiction: str = "",
    **semantic_fields,
) -> bytes:
    return json.dumps(
        {
            "schema_version": ("primary-legal-status-canonical-artifact-v1"),
            "source": source,
            "evidence_scope": evidence_scope,
            "source_record_identifier": source_record_identifier,
            "source_record_patent_number": patent_id,
            "application_number": application_number,
            "target_jurisdiction": target_jurisdiction,
            "raw_status": raw_status,
            **semantic_fields,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _odp_receipt():
    return build_primary_legal_status_receipt(
        patent_id="US-1234567-B2",
        source="uspto_odp_application",
        evidence_scope="application_prosecution",
        collection_mode="api",
        source_url="https://api.uspto.gov/api/v1/patent/applications/16123456",
        collected_at=_NOW,
        source_record_updated_at=_NOW - timedelta(hours=2),
        source_record_identifier="16123456",
        raw_status="Patented Case",
        normalized_outcome="patented",
        parser_result="conclusive",
        artifact=_official_odp_application_artifact(),
        artifact_media_type="application/json",
        parser_identity="uspto-odp-application-v1",
        limitations=_LIMITATIONS,
        attestation_key_id="current",
        attestation_key=_KEY,
    )


def test_receipt_is_bound_to_official_endpoint_artifact_and_server_key() -> None:
    receipt = _odp_receipt()

    assert receipt.patent_id == "US1234567B2"
    assert receipt.application_number == "16123456"
    assert receipt.source_record_patent_number == "US1234567"
    assert receipt.artifact_locator == (f"{receipt.source_url}#sha256={receipt.artifact_sha256}")
    assert receipt.artifact_payload["applicationNumberText"] == "16123456"
    assert receipt.authority_level == "primary"
    assert verify_primary_legal_status_receipt(
        receipt,
        attestation_keys={"current": _KEY},
    )
    assert not verify_primary_legal_status_receipt(
        receipt,
        attestation_keys={"current": b"wrong"},
    )


def test_report_bound_resolution_uses_outer_signature_without_worker_hmac_key() -> None:
    receipt = _odp_receipt()
    invalid_inner_signature = receipt.model_copy(update={"attestation_hmac_sha256": "0" * 64})

    assert verify_primary_legal_status_receipt_digest(invalid_inner_signature)
    assert not verify_primary_legal_status_receipt(
        invalid_inner_signature,
        attestation_keys={"current": _KEY},
    )
    resolution = resolve_report_bound_primary_legal_status_receipts(
        receipts=[invalid_inner_signature],
        requirements=[
            PrimaryLegalStatusRequirement(
                patent_id="US1234567B2",
                evidence_scope="application_prosecution",
            )
        ],
        now=_NOW,
    )
    assert resolution.coverage.satisfied

    corrupted_payload = receipt.model_copy(update={"raw_status": "Abandoned"})
    assert not verify_primary_legal_status_receipt_digest(corrupted_payload)
    corrupted_resolution = resolve_report_bound_primary_legal_status_receipts(
        receipts=[corrupted_payload],
        requirements=[
            PrimaryLegalStatusRequirement(
                patent_id="US1234567B2",
                evidence_scope="application_prosecution",
            )
        ],
        now=_NOW,
    )
    assert not corrupted_resolution.coverage.satisfied


def test_source_scope_and_endpoint_escalation_are_rejected() -> None:
    with pytest.raises(ValueError, match="scope exceeds"):
        build_primary_legal_status_receipt(
            patent_id="US1234567B2",
            source="uspto_odp_application",
            evidence_scope="claim_adjudication",
            collection_mode="api",
            source_url="https://api.uspto.gov/api/v1/patent/applications/16123456",
            collected_at=_NOW,
            source_record_identifier="16123456",
            raw_status="Claim 1 valid",
            normalized_outcome="claims_upheld",
            parser_result="conclusive",
            artifact=_canonical_artifact(
                source="uspto_odp_application",
                evidence_scope="claim_adjudication",
                source_record_identifier="16123456:decision",
                patent_id="US1234567",
                raw_status="Claims upheld",
                affected_claim_ids=["1"],
                adjudication_document_id="fake",
            ),
            artifact_media_type="application/json",
            parser_identity="fixture-v1",
            limitations=_LIMITATIONS,
            attestation_key_id="current",
            attestation_key=_KEY,
            affected_claim_ids=["1"],
            adjudication_document_id="fake",
        )

    with pytest.raises(ValueError, match="official endpoint"):
        build_primary_legal_status_receipt(
            patent_id="US1234567B2",
            source="uspto_odp_application",
            evidence_scope="application_prosecution",
            collection_mode="api",
            source_url="https://example.com/copied-record",
            collected_at=_NOW,
            source_record_identifier="16123456",
            raw_status="Patented Case",
            normalized_outcome="patented",
            parser_result="conclusive",
            artifact=_official_odp_application_artifact(),
            artifact_media_type="application/json",
            parser_identity="fixture-v1",
            limitations=_LIMITATIONS,
            attestation_key_id="current",
            attestation_key=_KEY,
        )


def test_ep_federated_register_cannot_satisfy_primary_national_requirement() -> None:
    federated = build_primary_legal_status_receipt(
        patent_id="EP1234567B1",
        source="epo_federated_register",
        evidence_scope="ep_national_post_grant",
        collection_mode="supervised_manual",
        source_url="https://register.epo.org/application?number=EP1234567",
        collected_at=_NOW,
        source_record_identifier="EP1234567:DE",
        raw_status="In force",
        normalized_outcome="active",
        parser_result="conclusive",
        artifact=_canonical_artifact(
            source="epo_federated_register",
            evidence_scope="ep_national_post_grant",
            source_record_identifier="EP1234567:DE",
            patent_id="EP1234567B1",
            raw_status="In force",
            target_jurisdiction="DE",
        ),
        artifact_media_type="application/json",
        parser_identity="supervised-federated-import-v1",
        limitations=[
            "Federated Register national data is supplementary; use the national authority."
        ],
        attestation_key_id="current",
        attestation_key=_KEY,
        target_jurisdiction="DE",
    )

    coverage = evaluate_primary_legal_status_coverage(
        receipts=[federated],
        requirements=[
            PrimaryLegalStatusRequirement(
                patent_id="EP1234567B1",
                evidence_scope="ep_national_post_grant",
                target_jurisdiction="DE",
            )
        ],
        attestation_keys={"current": _KEY},
        now=_NOW,
    )

    assert coverage.satisfied is False
    assert "EP1234567B1" in coverage.failure_reasons[0]


def test_pinned_national_register_satisfies_target_state_but_stale_receipt_fails() -> None:
    authority = NationalRegisterAuthority(
        jurisdiction="DE",
        authority_name="German Patent and Trade Mark Office",
        allowed_hosts=["register.dpma.de"],
        verified_from_url=(
            "https://www.epo.org/en/searching-for-patents/legal/register/"
            "documentation/federated-register"
        ),
        verified_at=_NOW,
    )
    national = build_primary_legal_status_receipt(
        patent_id="EP1234567B1",
        source="ep_national_register",
        evidence_scope="ep_national_post_grant",
        collection_mode="supervised_manual",
        source_url="https://register.dpma.de/DPMAregister/pat/register",
        collected_at=_NOW - timedelta(hours=24),
        source_record_identifier="DE:EP1234567",
        raw_status="Patent in force",
        normalized_outcome="active",
        parser_result="conclusive",
        artifact=_canonical_artifact(
            source="ep_national_register",
            evidence_scope="ep_national_post_grant",
            source_record_identifier="DE:EP1234567",
            patent_id="EP1234567B1",
            raw_status="Patent in force",
            target_jurisdiction="DE",
        ),
        artifact_media_type="application/json",
        parser_identity="supervised-national-register-import-v1",
        limitations=[
            "Status is limited to the identified national validation and collection time."
        ],
        attestation_key_id="current",
        attestation_key=_KEY,
        target_jurisdiction="DE",
        national_authority=authority,
    )
    requirement = PrimaryLegalStatusRequirement(
        patent_id="EP1234567B1",
        evidence_scope="ep_national_post_grant",
        target_jurisdiction="DE",
    )

    assert evaluate_primary_legal_status_coverage(
        receipts=[national],
        requirements=[requirement],
        attestation_keys={"current": _KEY},
        now=_NOW,
    ).satisfied
    assert not evaluate_primary_legal_status_coverage(
        receipts=[national],
        requirements=[requirement],
        attestation_keys={"current": _KEY},
        now=_NOW + timedelta(hours=49),
    ).satisfied


def test_us_maintenance_status_requires_supervised_storefront_artifact() -> None:
    with pytest.raises(ValueError, match="collection mode"):
        build_primary_legal_status_receipt(
            patent_id="US1234567B2",
            source="uspto_maintenance_storefront",
            evidence_scope="patent_maintenance",
            collection_mode="api",
            source_url="https://fees.uspto.gov/MaintenanceFees",
            collected_at=_NOW,
            source_record_identifier="US1234567",
            raw_status="Maintenance fee paid",
            normalized_outcome="paid",
            parser_result="conclusive",
            artifact=_canonical_artifact(
                source="uspto_maintenance_storefront",
                evidence_scope="patent_maintenance",
                source_record_identifier="US1234567",
                patent_id="US1234567B2",
                raw_status="Maintenance fee paid",
            ),
            artifact_media_type="application/json",
            parser_identity="fixture-v1",
            limitations=["No official public maintenance-fee API is documented."],
            attestation_key_id="current",
            attestation_key=_KEY,
        )


def test_inconclusive_signed_receipt_cannot_satisfy_coverage() -> None:
    receipt = build_primary_legal_status_receipt(
        patent_id="US1234567B2",
        source="uspto_maintenance_storefront",
        evidence_scope="patent_maintenance",
        collection_mode="supervised_manual",
        source_url="https://fees.uspto.gov/MaintenanceFees",
        collected_at=_NOW,
        source_record_identifier="US1234567",
        raw_status="UNKNOWN / unable to determine",
        normalized_outcome="unknown",
        parser_result="inconclusive",
        artifact=_canonical_artifact(
            source="uspto_maintenance_storefront",
            evidence_scope="patent_maintenance",
            source_record_identifier="US1234567",
            patent_id="US1234567B2",
            raw_status="UNKNOWN / unable to determine",
        ),
        artifact_media_type="application/json",
        parser_identity="supervised-uspto-maintenance-v1",
        limitations=["No conclusion"],
        attestation_key_id="current",
        attestation_key=_KEY,
    )

    coverage = evaluate_primary_legal_status_coverage(
        receipts=[receipt],
        requirements=[
            PrimaryLegalStatusRequirement(
                patent_id="US1234567B2",
                evidence_scope="patent_maintenance",
            )
        ],
        attestation_keys={"current": _KEY},
        now=_NOW,
    )

    assert coverage.satisfied is False


def test_declared_outcome_must_match_approved_parser_replay() -> None:
    with pytest.raises(ValueError, match="replay"):
        build_primary_legal_status_receipt(
            patent_id="US1234567B2",
            source="uspto_maintenance_storefront",
            evidence_scope="patent_maintenance",
            collection_mode="supervised_manual",
            source_url="https://fees.uspto.gov/MaintenanceFees",
            collected_at=_NOW,
            source_record_identifier="US1234567",
            raw_status="UNKNOWN / unable to determine",
            normalized_outcome="paid",
            parser_result="conclusive",
            artifact=_canonical_artifact(
                source="uspto_maintenance_storefront",
                evidence_scope="patent_maintenance",
                source_record_identifier="US1234567",
                patent_id="US1234567B2",
                raw_status="UNKNOWN / unable to determine",
            ),
            artifact_media_type="application/json",
            parser_identity="supervised-uspto-maintenance-v1",
            limitations=["No conclusion"],
            attestation_key_id="current",
            attestation_key=_KEY,
        )


def test_primary_receipt_rejects_short_attestation_key() -> None:
    with pytest.raises(ValueError, match="attestation"):
        build_primary_legal_status_receipt(
            patent_id="US1234567B2",
            source="uspto_odp_application",
            evidence_scope="application_prosecution",
            collection_mode="api",
            source_url="https://api.uspto.gov/api/v1/patent/applications/16123456",
            collected_at=_NOW,
            source_record_identifier="16123456",
            raw_status="Patented Case",
            normalized_outcome="patented",
            parser_result="conclusive",
            artifact=b"fixture",
            artifact_media_type="application/json",
            parser_identity="uspto-odp-application-v1",
            limitations=_LIMITATIONS,
            attestation_key_id="current",
            attestation_key=b"k",
        )


def test_garbage_and_wrong_application_or_patent_cannot_be_signed() -> None:
    common = {
        "patent_id": "US1234567B2",
        "source": "uspto_odp_application",
        "evidence_scope": "application_prosecution",
        "collection_mode": "api",
        "source_url": ("https://api.uspto.gov/api/v1/patent/applications/16123456"),
        "collected_at": _NOW,
        "artifact_media_type": "application/json",
        "limitations": _LIMITATIONS,
        "attestation_key_id": "current",
        "attestation_key": _KEY,
    }

    with pytest.raises(ValueError, match="applicationMetaData"):
        build_primary_legal_status_receipt(
            **common,
            artifact=b'{"garbage":true}',
        )

    with pytest.raises(ValueError, match=r"application|source record"):
        build_primary_legal_status_receipt(
            **common,
            source_record_identifier="16123456",
            artifact=_official_odp_application_artifact(application_number="99999999"),
        )

    with pytest.raises(ValueError, match="receipt patent"):
        build_primary_legal_status_receipt(
            **common,
            artifact=_official_odp_application_artifact(patent_number="US7654321"),
        )


def test_term_fields_must_replay_from_the_retained_artifact() -> None:
    artifact = _canonical_artifact(
        source="uspto_odp_application",
        evidence_scope="patent_term",
        source_record_identifier="16123456",
        patent_id="US1234567",
        application_number="16123456",
        raw_status="Current term",
        term_end_date="2035-01-01",
        term_basis_document_ids=["grant", "pta-adjustment"],
    )

    with pytest.raises(ValueError, match="replay"):
        build_primary_legal_status_receipt(
            patent_id="US1234567B2",
            source="uspto_odp_application",
            evidence_scope="patent_term",
            collection_mode="api",
            source_url=("https://api.uspto.gov/api/v1/patent/applications/16123456/adjustment"),
            collected_at=_NOW,
            artifact=artifact,
            artifact_media_type="application/json",
            limitations=["Term is limited to the retained adjustment record."],
            attestation_key_id="current",
            attestation_key=_KEY,
            term_end_date=date(2040, 1, 1),
            term_basis_document_ids=["grant", "pta-adjustment"],
        )

    valid = build_primary_legal_status_receipt(
        patent_id="US1234567B2",
        source="uspto_odp_application",
        evidence_scope="patent_term",
        collection_mode="api",
        source_url=("https://api.uspto.gov/api/v1/patent/applications/16123456/adjustment"),
        collected_at=_NOW,
        artifact=artifact,
        artifact_media_type="application/json",
        limitations=["Term is limited to the retained adjustment record."],
        attestation_key_id="current",
        attestation_key=_KEY,
    )
    invented_term = valid.model_copy(update={"term_end_date": date(2040, 1, 1)})
    assert not verify_primary_legal_status_receipt(
        invented_term,
        attestation_keys={"current": _KEY},
    )


def test_verifier_replays_the_embedded_retained_artifact() -> None:
    receipt = _odp_receipt()
    tampered_payload = dict(receipt.artifact_payload)
    tampered_metadata = dict(tampered_payload["applicationMetaData"])
    tampered_metadata["applicationStatusDescriptionText"] = "Abandoned"
    tampered_payload["applicationMetaData"] = tampered_metadata
    tampered = receipt.model_copy(update={"artifact_payload": tampered_payload})

    assert not verify_primary_legal_status_receipt(
        tampered,
        attestation_keys={"current": _KEY},
    )


def test_term_issuer_replays_exact_bound_odp_records() -> None:
    receipt = issue_uspto_odp_patent_term_receipt(
        patent_id="US1234567B2",
        application_record=_term_application_record(),
        adjustment_response=_term_adjustment_response(),
        continuity_response=_term_continuity_response(),
        documents_response=_term_documents_response(),
        collected_at=_NOW,
        attestation_key_id="current",
        attestation_key=_KEY,
    )

    assert receipt.normalized_outcome == "term_current"
    assert receipt.term_end_date == date(2030, 1, 11)
    assert verify_primary_legal_status_receipt(
        receipt,
        attestation_keys={"current": _KEY},
    )


def test_term_issuer_rejects_cross_application_and_incomplete_records() -> None:
    wrong_documents = _term_documents_response()
    wrong_documents["applicationNumberText"] = "99999999"
    with pytest.raises(ValueError, match="target application"):
        issue_uspto_odp_patent_term_receipt(
            patent_id="US1234567B2",
            application_record=_term_application_record(),
            adjustment_response=_term_adjustment_response(),
            continuity_response=_term_continuity_response(),
            documents_response=wrong_documents,
            collected_at=_NOW,
            attestation_key_id="current",
            attestation_key=_KEY,
        )

    contradictory_documents = _term_documents_response()
    contradictory_documents["totalNumFound"] = 1
    with pytest.raises(ValueError, match=r"incomplete|paginated"):
        issue_uspto_odp_patent_term_receipt(
            patent_id="US1234567B2",
            application_record=_term_application_record(),
            adjustment_response=_term_adjustment_response(),
            continuity_response=_term_continuity_response(),
            documents_response=contradictory_documents,
            collected_at=_NOW,
            attestation_key_id="current",
            attestation_key=_KEY,
        )


def test_term_issuer_rejects_unknown_continuity_and_terminal_disclaimer() -> None:
    unknown_continuity = _term_continuity_response()
    unknown_continuity["parentContinuityBag"] = [
        {
            "parentApplicationNumberText": "12111111",
            "parentFilingDate": "2000-01-01",
        }
    ]
    with pytest.raises(ValueError, match="classify a continuity"):
        issue_uspto_odp_patent_term_receipt(
            patent_id="US1234567B2",
            application_record=_term_application_record(),
            adjustment_response=_term_adjustment_response(),
            continuity_response=unknown_continuity,
            documents_response=_term_documents_response(),
            collected_at=_NOW,
            attestation_key_id="current",
            attestation_key=_KEY,
        )

    disclaimer_documents = _term_documents_response()
    disclaimer_documents["count"] = 1
    disclaimer_documents["results"] = [
        {
            "documentIdentifier": "DIST-1",
            "documentCode": "DIST",
        }
    ]
    with pytest.raises(ValueError, match="terminal-disclaimer"):
        issue_uspto_odp_patent_term_receipt(
            patent_id="US1234567B2",
            application_record=_term_application_record(),
            adjustment_response=_term_adjustment_response(),
            continuity_response=_term_continuity_response(),
            documents_response=disclaimer_documents,
            collected_at=_NOW,
            attestation_key_id="current",
            attestation_key=_KEY,
        )


def _ptab_exchange(*, count: int = 0, total: int = 0) -> dict[str, object]:
    return {
        "request": {
            "q": "patentOwnerData.patentNumber:1234567",
            "pagination": {"offset": 0, "limit": 1000},
        },
        "response": {
            "count": count,
            "totalNumFound": total,
            "results": [],
        },
    }


def test_ptab_negative_receipt_requires_exact_query_and_complete_zero() -> None:
    receipt = issue_uspto_odp_ptab_status_receipt(
        patent_id="US1234567B2",
        proceedings_exchange=_ptab_exchange(),
        decision_exchanges={},
        collected_at=_NOW,
        attestation_key_id="current",
        attestation_key=_KEY,
    )
    assert receipt.normalized_outcome == "none_found"
    assert verify_primary_legal_status_receipt(
        receipt,
        attestation_keys={"current": _KEY},
    )

    contradictory = _ptab_exchange(total=1)
    with pytest.raises(ValueError, match=r"incomplete|paginated"):
        issue_uspto_odp_ptab_status_receipt(
            patent_id="US1234567B2",
            proceedings_exchange=contradictory,
            decision_exchanges={},
            collected_at=_NOW,
            attestation_key_id="current",
            attestation_key=_KEY,
        )

    wrong_query = _ptab_exchange()
    wrong_query["request"] = {
        "q": "patentOwnerData.patentNumber:9999999",
        "pagination": {"offset": 0, "limit": 1000},
    }
    with pytest.raises(ValueError, match="receipt patent"):
        issue_uspto_odp_ptab_status_receipt(
            patent_id="US1234567B2",
            proceedings_exchange=wrong_query,
            decision_exchanges={},
            collected_at=_NOW,
            attestation_key_id="current",
            attestation_key=_KEY,
        )


def test_ptab_pending_receipt_requires_production_shape() -> None:
    exchange = _ptab_exchange(count=1, total=1)
    response = exchange["response"]
    assert isinstance(response, dict)
    response["results"] = [
        {
            "trialNumber": "IPR2025-00001",
            "patentOwnerData": {"patentNumber": "1234567"},
            "trialMetaData": {"trialStatusCategory": "Instituted"},
        }
    ]
    receipt = issue_uspto_odp_ptab_status_receipt(
        patent_id="US1234567B2",
        proceedings_exchange=exchange,
        decision_exchanges={},
        collected_at=_NOW,
        attestation_key_id="current",
        attestation_key=_KEY,
    )
    assert receipt.normalized_outcome == "pending"


def test_ptab_completed_proceeding_is_withheld_without_controlling_text() -> None:
    exchange = _ptab_exchange(count=1, total=1)
    response = exchange["response"]
    assert isinstance(response, dict)
    response["results"] = [
        {
            "trialNumber": "IPR2025-00001",
            "patentOwnerData": {"patentNumber": "1234567"},
            "trialMetaData": {"trialStatusCategory": "Final Written Decision"},
        }
    ]
    with pytest.raises(ValueError, match="controlling decision/certificate text"):
        issue_uspto_odp_ptab_status_receipt(
            patent_id="US1234567B2",
            proceedings_exchange=exchange,
            decision_exchanges={
                "IPR2025-00001": {
                    "request": {
                        "q": "trialNumber:IPR2025-00001",
                        "pagination": {"offset": 0, "limit": 1000},
                    },
                    "response": {
                        "count": 1,
                        "totalNumFound": 1,
                        "results": [
                            {
                                "trialNumber": "IPR2025-00001",
                                "decisionData": {"decisionTypeCategory": "Final Written Decision"},
                            }
                        ],
                    },
                }
            },
            collected_at=_NOW,
            attestation_key_id="current",
            attestation_key=_KEY,
        )


def _maintenance_import(
    *,
    observed_at: datetime,
    approved_at: datetime,
) -> SupervisedMaintenanceImport:
    statement = b"official USPTO maintenance statement fixture"
    return SupervisedMaintenanceImport(
        patent_number="US1234567B2",
        application_number="16123456",
        source_record_identifier="statement-2026-07-26",
        raw_status="Maintenance fee paid",
        storefront_observed_at=observed_at,
        official_statement_identifier="statement-2026-07-26",
        official_statement_sha256=hashlib.sha256(statement).hexdigest(),
        official_statement_base64=base64.b64encode(statement).decode("ascii"),
        collector_user_id="collector-user",
        supervisor_user_id="supervising-attorney",
        supervisor_role="attorney",
        approved_at=approved_at,
    )


def test_supervised_maintenance_receipt_retains_bytes_and_uses_observation_freshness() -> None:
    maintenance_import = _maintenance_import(
        observed_at=_NOW - timedelta(hours=2),
        approved_at=_NOW,
    )
    receipt = issue_supervised_uspto_maintenance_receipt(
        maintenance_import=maintenance_import,
        collected_at=_NOW,
        attestation_key_id="current",
        attestation_key=_KEY,
    )
    assert receipt.normalized_outcome == "paid"
    assert verify_primary_legal_status_receipt(
        receipt,
        attestation_keys={"current": _KEY},
    )
    requirement = PrimaryLegalStatusRequirement(
        patent_id="US1234567B2",
        evidence_scope="patent_maintenance",
    )
    assert evaluate_primary_legal_status_coverage(
        receipts=[receipt],
        requirements=[requirement],
        attestation_keys={"current": _KEY},
        now=_NOW,
    ).satisfied
    assert not evaluate_primary_legal_status_coverage(
        receipts=[receipt],
        requirements=[requirement],
        attestation_keys={"current": _KEY},
        now=_NOW + timedelta(hours=71),
    ).satisfied


def test_maintenance_import_rejects_self_approval_stale_review_and_wrong_bytes() -> None:
    statement = b"official"
    common = {
        "patent_number": "US1234567B2",
        "application_number": "16123456",
        "source_record_identifier": "statement-1",
        "raw_status": "Maintenance fee paid",
        "storefront_observed_at": _NOW - timedelta(hours=5),
        "official_statement_identifier": "statement-1",
        "official_statement_sha256": hashlib.sha256(statement).hexdigest(),
        "official_statement_base64": base64.b64encode(statement).decode("ascii"),
        "collector_user_id": "same-user",
        "supervisor_user_id": "same-user",
        "supervisor_role": "attorney",
        "approved_at": _NOW,
    }
    with pytest.raises(ValueError, match="independent supervision"):
        SupervisedMaintenanceImport.model_validate(common)
    with pytest.raises(ValueError, match="too remote"):
        SupervisedMaintenanceImport.model_validate(
            {
                **common,
                "supervisor_user_id": "attorney",
            }
        )
    with pytest.raises(ValueError, match="digest"):
        SupervisedMaintenanceImport.model_validate(
            {
                **common,
                "storefront_observed_at": _NOW,
                "supervisor_user_id": "attorney",
                "official_statement_base64": base64.b64encode(b"wrong").decode("ascii"),
            }
        )


def test_receipt_winner_uses_source_evidence_time_not_later_collection() -> None:
    def _receipt(
        *,
        raw_status: str,
        observed_at: datetime,
        collected_at: datetime,
    ) -> PrimaryLegalStatusReceipt:
        return build_primary_legal_status_receipt(
            patent_id="US1234567B2",
            source="uspto_maintenance_storefront",
            evidence_scope="patent_maintenance",
            collection_mode="supervised_manual",
            source_url="https://fees.uspto.gov/MaintenanceFees",
            collected_at=collected_at,
            source_record_updated_at=observed_at,
            artifact=_canonical_artifact(
                source="uspto_maintenance_storefront",
                evidence_scope="patent_maintenance",
                source_record_identifier=f"statement:{observed_at.isoformat()}",
                patent_id="US1234567B2",
                raw_status=raw_status,
            ),
            artifact_media_type="application/json",
            limitations=["Fixture exercises effective evidence time selection."],
            attestation_key_id="current",
            attestation_key=_KEY,
        )

    newer_evidence = _receipt(
        raw_status="Expired for failure to pay maintenance fee",
        observed_at=_NOW - timedelta(hours=1),
        collected_at=_NOW - timedelta(minutes=30),
    )
    later_collection_of_older_evidence = _receipt(
        raw_status="Maintenance fee paid",
        observed_at=_NOW - timedelta(hours=2),
        collected_at=_NOW,
    )
    from praviar_pipeline.clients.primary_legal_status import (
        resolve_primary_legal_status_receipts,
    )

    resolution = resolve_primary_legal_status_receipts(
        receipts=[newer_evidence, later_collection_of_older_evidence],
        requirements=[
            PrimaryLegalStatusRequirement(
                patent_id="US1234567B2",
                evidence_scope="patent_maintenance",
            )
        ],
        attestation_keys={"current": _KEY},
        now=_NOW,
    )

    assert resolution.coverage.satisfied
    assert resolution.selected_receipts[0].normalized_outcome == "lapsed"


@pytest.mark.asyncio
async def test_application_enrichment_issues_a_replayable_production_receipt(
    monkeypatch,
) -> None:
    class _KeyRing:
        active_key_id = "current"

        @staticmethod
        def active_key() -> bytes:
            return _KEY

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get_application_data(self, _patent_id: str) -> dict:
            return _term_application_record()

        async def get_adjustment(self, _patent_id: str) -> dict:
            return _term_adjustment_response()

        async def get_continuity_artifact(self, _patent_id: str) -> dict:
            return _term_continuity_response()

        async def get_file_wrapper_documents_artifact(
            self,
            _patent_id: str,
        ) -> dict:
            return _term_documents_response()

    monkeypatch.setattr(
        enrichment,
        "get_settings",
        lambda: SimpleNamespace(
            uspto_odp_api_key="configured",
            search_max_patent_term_calc=5,
            checkpoint_integrity_keys=_KeyRing(),
        ),
    )
    hit = PatentHit(patent_id="US1234567B2", is_granted=True)

    enriched = await enrichment.enrich_application_data(
        [hit],
        client_factory=_Client,
    )

    assert enriched == 1
    assert hit.application_number == "16123456"
    assert len(hit.primary_legal_status_receipts) == 2
    receipts = [
        PrimaryLegalStatusReceipt.model_validate(raw) for raw in hit.primary_legal_status_receipts
    ]
    assert all(
        verify_primary_legal_status_receipt(
            receipt,
            attestation_keys={"current": _KEY},
        )
        for receipt in receipts
    )
    by_scope = {receipt.evidence_scope: receipt for receipt in receipts}
    assert (
        by_scope["application_prosecution"].artifact_payload["applicationMetaData"][
            "applicationStatusDescriptionText"
        ]
        == "Patented Case"
    )
    assert by_scope["patent_term"].term_end_date == date(2030, 1, 11)


@pytest.mark.asyncio
async def test_ptab_enrichment_issues_complete_negative_receipt(
    monkeypatch,
) -> None:
    class _KeyRing:
        active_key_id = "current"

        @staticmethod
        def active_key() -> bytes:
            return _KEY

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get_proceedings_artifact(
            self,
            _patent_id: str,
        ) -> dict[str, object]:
            return _ptab_exchange()

        async def get_decisions_artifact(
            self,
            _trial_number: str,
        ) -> dict[str, object]:
            raise AssertionError("empty PTAB response has no decisions")

    monkeypatch.setattr(
        enrichment,
        "get_settings",
        lambda: SimpleNamespace(
            uspto_odp_api_key="configured",
            checkpoint_integrity_keys=_KeyRing(),
        ),
    )
    hit = PatentHit(patent_id="US1234567B2", is_granted=True)

    outcome = await enrichment.enrich_ptab_proceedings(
        [hit],
        client_factory=_Client,
    )

    assert outcome.attempted_count == 1
    assert outcome.covered_count == 1
    assert outcome.evidence_count == 0
    receipt = PrimaryLegalStatusReceipt.model_validate(hit.primary_legal_status_receipts[0])
    assert receipt.normalized_outcome == "none_found"
    assert verify_primary_legal_status_receipt(
        receipt,
        attestation_keys={"current": _KEY},
    )

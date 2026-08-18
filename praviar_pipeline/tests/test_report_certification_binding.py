from __future__ import annotations

from copy import deepcopy

from certification_keyring_fixtures import (
    TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET,
    build_test_report_certification_keyrings,
)

from praviar_pipeline.report_certification_binding import (
    REPORT_BINDING_FIELD,
    ReportCertificationSigner,
    ReportCertificationVerificationKeyRing,
    sign_report_certification_binding,
    verify_report_certification_binding,
)


def _report() -> dict:
    return {
        "report_id": "report-1",
        "clearance_decision": {"decision": "clear"},
        "decision_scope": {"jurisdictions": ["US"]},
        "certification_scope": {
            "evidence_verified": True,
            "evidence_receipt_id": "receipt-1",
            "evidence_receipt_sha256": "b" * 64,
            "evidence_pipeline_git_sha": "a" * 40,
            "verified_lane_ids": ["us-small-molecule-compound-adaptive-v1"],
        },
        "result": {"summary": "No blocking exposure found."},
    }


def _signer() -> ReportCertificationSigner:
    return ReportCertificationSigner.from_secret(TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET)


def _keyring() -> ReportCertificationVerificationKeyRing:
    return ReportCertificationVerificationKeyRing.from_json(
        TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING
    )


def _sign(report: dict, *, analysis_id: str = "analysis-1", org_id: str = "org-1") -> dict:
    return sign_report_certification_binding(
        report,
        signer=_signer(),
        analysis_id=analysis_id,
        org_id=org_id,
    )


def test_report_binding_verifies_exact_report_receipt_and_lane() -> None:
    report = _report()
    report[REPORT_BINDING_FIELD] = _sign(report)

    assert (
        verify_report_certification_binding(
            report,
            keyring=_keyring(),
            expected_analysis_id="analysis-1",
            expected_org_id="org-1",
        )
        == []
    )


def test_report_binding_normalizes_absent_optional_certification_fields() -> None:
    report = {
        "report_id": "report-unclear",
        "clearance_decision": {"decision": "unclear"},
        "certification_scope": {},
    }
    report[REPORT_BINDING_FIELD] = _sign(report)

    assert (
        verify_report_certification_binding(
            report,
            keyring=_keyring(),
            expected_analysis_id="analysis-1",
            expected_org_id="org-1",
        )
        == []
    )


def test_report_binding_rejects_post_completion_mutation() -> None:
    report = _report()
    report[REPORT_BINDING_FIELD] = _sign(report)
    report["result"]["summary"] = "Mutated conclusion"

    assert verify_report_certification_binding(report, keyring=_keyring()) == [
        "report_certification_binding_subject_mismatch"
    ]


def test_report_binding_cannot_be_replayed_across_receipts() -> None:
    report = _report()
    binding = _sign(report)
    replayed = deepcopy(report)
    replayed["certification_scope"]["evidence_receipt_id"] = "receipt-2"
    replayed[REPORT_BINDING_FIELD] = binding

    failures = verify_report_certification_binding(replayed, keyring=_keyring())

    assert failures


def test_report_binding_cannot_be_replayed_across_analysis_or_org() -> None:
    report = _report()
    report[REPORT_BINDING_FIELD] = _sign(report)

    assert verify_report_certification_binding(
        report,
        keyring=_keyring(),
        expected_analysis_id="analysis-2",
        expected_org_id="org-1",
    ) == ["report_certification_binding_owner_mismatch"]
    assert verify_report_certification_binding(
        report,
        keyring=_keyring(),
        expected_analysis_id="analysis-1",
        expected_org_id="org-2",
    ) == ["report_certification_binding_owner_mismatch"]


def test_historical_report_survives_overlapping_signer_rotation() -> None:
    old_signer = _signer()
    new_signing_keyring, _ = build_test_report_certification_keyrings(key_id="test-report-v3")
    new_signer = ReportCertificationSigner.from_secret(new_signing_keyring)
    combined_signer = ReportCertificationSigner(
        active_key_id=new_signer.active_key_id,
        private_keys={**old_signer.private_keys, **new_signer.private_keys},
    )
    report = _report()
    report[REPORT_BINDING_FIELD] = sign_report_certification_binding(
        report,
        signer=old_signer,
        analysis_id="analysis-1",
        org_id="org-1",
    )

    overlapping_public_ring = ReportCertificationVerificationKeyRing.from_json(
        combined_signer.public_keyring().to_json()
    )

    assert (
        verify_report_certification_binding(
            report,
            keyring=overlapping_public_ring,
            expected_analysis_id="analysis-1",
            expected_org_id="org-1",
        )
        == []
    )


def test_historical_report_fails_closed_after_signer_key_is_retired() -> None:
    report = _report()
    report[REPORT_BINDING_FIELD] = _sign(report)
    replacement_signing_keyring, _ = build_test_report_certification_keyrings(
        key_id="test-report-v3"
    )
    replacement_signer = ReportCertificationSigner.from_secret(replacement_signing_keyring)

    assert verify_report_certification_binding(
        report,
        keyring=replacement_signer.public_keyring(),
    ) == ["report_certification_binding_key_unavailable"]


def test_api_public_keyring_cannot_sign_or_recover_private_key() -> None:
    keyring = _keyring()

    assert not hasattr(keyring, "sign")
    assert all(not hasattr(key, "private_bytes") for key in keyring.keys.values())


def test_v1_hmac_binding_is_rejected_without_compatibility_path() -> None:
    report = _report()
    report[REPORT_BINDING_FIELD] = {
        "schema_version": "praviar.report-certification-binding.v1",
        "algorithm": "HMAC-SHA256",
    }

    assert verify_report_certification_binding(report, keyring=_keyring()) == [
        "report_certification_binding_missing_or_invalid"
    ]

"""Tests for claim-source support map construction."""

from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)
from praviar_pipeline.models.analysis import ElementStatus, RiskLevel
from praviar_pipeline.models.patent import PatentHit, PatentSource, build_claim_text_provenance
from praviar_pipeline.models.report_source_spans import (
    UnsupportedCustomerVisibleClaimError,
    build_claim_source_span_map,
    ensure_no_unsupported_customer_visible_claims,
    verify_source_span_attestation,
)
from praviar_pipeline.pipeline.runtime.live_collector_claims import (
    record_claims_text_retrieval,
)


def _analysis(*, evidence: str = "", spec_citation: str = "", status=ElementStatus.MET):
    element = SimpleNamespace(
        element_number=1,
        element_text="a compound comprising X",
        status=status,
        reasoning="X maps to the target substituent",
        evidence=evidence,
        spec_citation=spec_citation,
    )
    claim = SimpleNamespace(claim_number=1, elements=[element])
    return SimpleNamespace(
        patent_id="US1234567B2",
        risk_level=RiskLevel.HIGH,
        claims_analyzed=[claim],
    )


def _patent_details(claims_text: str = "1. a compound comprising X") -> dict[str, dict]:
    provenance = build_claim_text_provenance(
        patent_id="US1234567B2",
        claims_text=claims_text,
        source=PatentSource.PATENTSVIEW,
        artifact_locator=("https://search.patentsview.org/api/v1/patent/?patent_id=US1234567B2"),
        collector_identity="runtime.patentsview_claims",
    )
    return {
        "US1234567B2": {
            "claims_text": claims_text,
            "claims_text_source": "patentsview",
            "claims_text_provenance": provenance.model_dump(mode="json"),
        }
    }


def _trusted_evidence_bundle(
    claims_text: str = "1. a compound comprising X",
) -> tuple[dict[str, dict], PatentHit, CheckpointIntegrityKeyRing]:
    hit = PatentHit(
        patent_id="US1234567B2",
        jurisdiction="US",
        sources=[PatentSource.PATENTSVIEW],
    )
    record_claims_text_retrieval(
        hit,
        claims_text,
        source=PatentSource.PATENTSVIEW,
        collector_identity="runtime.patentsview_claims",
        upstream_locator=("https://search.patentsview.org/api/v1/patent/?patent_id=US1234567B2"),
    )
    keyring = CheckpointIntegrityKeyRing.from_secret(DEV_CHECKPOINT_HMAC_KEYRING_SECRET)
    return (
        {"US1234567B2": hit.model_dump(mode="json")},
        hit,
        keyring,
    )


def test_claim_source_span_map_separates_source_text_from_mapping_support() -> None:
    details, hit, keyring = _trusted_evidence_bundle()
    support_map = build_claim_source_span_map(
        [_analysis(evidence="Example 3 discloses X", spec_citation="col. 5, lines 1-7")],
        details,
        trusted_patent_hits=[hit],
        evidence_attestation_key_id=keyring.active_key_id,
        evidence_attestation_key=keyring.active_key(),
        evidence_attestation_subject_id="report-123",
    )

    assert len(support_map.entries) == 2
    entry, source_entry = support_map.entries
    assert entry.support_status == "needs_review"
    assert entry.review_required is True
    assert source_entry.support_status == "supported"
    assert source_entry.report_section == "verified_claim_text"
    assert support_map.unsupported_customer_visible_claim_count == 0
    assert len(entry.source_span_ids) == 3
    verified = [
        support_map.spans[span_id]
        for span_id in source_entry.source_span_ids
        if support_map.spans[span_id].source_type == "verified_claim_text"
    ]
    assert len(verified) == 1
    assert verified[0].source_name == "patentsview"
    assert len(verified[0].source_text_sha256) == 64
    assert verified[0].source_artifact_locator.startswith("https://search.patentsview.org/")
    assert "#sha256=" in verified[0].source_artifact_locator
    assert verified[0].collector_identity == "runtime.patentsview_claims"
    assert verified[0].collector_version
    assert len(verified[0].provenance_cassette_sha256) == 64
    assert verify_source_span_attestation(
        verified[0],
        verification_key=keyring.active_key(),
        expected_subject_id="report-123",
    )
    assert {support_map.spans[span_id].source_type for span_id in entry.source_span_ids}.isdisjoint(
        {"element_evidence", "specification_citation"}
    )
    assert set(support_map.spans) == set(entry.source_span_ids)


def test_serialized_claim_provenance_cannot_issue_a_durable_receipt_by_itself() -> None:
    details, _hit, keyring = _trusted_evidence_bundle()

    support_map = build_claim_source_span_map(
        [_analysis()],
        details,
        trusted_patent_hits=[],
        evidence_attestation_key_id=keyring.active_key_id,
        evidence_attestation_key=keyring.active_key(),
        evidence_attestation_subject_id="report-123",
    )

    assert all(span.source_type != "verified_claim_text" for span in support_map.spans.values())


def test_durable_receipt_rejects_cross_report_replay_and_tampering() -> None:
    details, hit, keyring = _trusted_evidence_bundle()
    support_map = build_claim_source_span_map(
        [_analysis()],
        details,
        trusted_patent_hits=[hit],
        evidence_attestation_key_id=keyring.active_key_id,
        evidence_attestation_key=keyring.active_key(),
        evidence_attestation_subject_id="report-123",
    )
    verified = next(
        span for span in support_map.spans.values() if span.source_type == "verified_claim_text"
    )

    assert not verify_source_span_attestation(
        verified,
        verification_key=keyring.active_key(),
        expected_subject_id="report-other",
    )
    assert not verify_source_span_attestation(
        verified.model_copy(update={"excerpt": "tampered"}),
        verification_key=keyring.active_key(),
        expected_subject_id="report-123",
    )


def test_claim_text_without_artifact_grade_provenance_fails_closed() -> None:
    support_map = build_claim_source_span_map(
        [_analysis(evidence="model-authored evidence")],
        {
            "US1234567B2": {
                "claims_text": "a compound comprising X",
                "claims_text_source": "patentsview",
            }
        },
    )

    assert len(support_map.entries) == 1
    assert support_map.entries[0].support_status == "needs_review"
    assert all(span.source_type != "verified_claim_text" for span in support_map.spans.values())


def test_tampered_claim_text_invalidates_provenance_support() -> None:
    details = _patent_details()
    details["US1234567B2"]["claims_text"] += " tampered"

    support_map = build_claim_source_span_map([_analysis()], details)

    assert all(span.source_type != "verified_claim_text" for span in support_map.spans.values())


def test_claim_source_span_map_marks_no_evidence_as_needs_review() -> None:
    # Elements with a determination but no evidence/spec_citation are flagged for
    # human review rather than hard-blocking the pipeline.
    support_map = build_claim_source_span_map([_analysis()])

    entry = support_map.entries[0]
    assert entry.support_status == "needs_review"
    assert entry.review_required is True
    assert support_map.unsupported_customer_visible_claim_count == 0
    assert support_map.needs_review_count == 1


def test_model_authored_evidence_and_citation_cannot_establish_support() -> None:
    support_map = build_claim_source_span_map(
        [_analysis(evidence="Invented example", spec_citation="invented col. 99")],
        _patent_details("different retrieved claim text"),
    )

    assert support_map.entries[0].support_status == "needs_review"
    assert {
        support_map.spans[span_id].source_type for span_id in support_map.entries[0].source_span_ids
    }.isdisjoint({"verified_claim_text", "element_evidence", "specification_citation"})


def test_claim_source_span_map_unclear_elements_need_review() -> None:
    support_map = build_claim_source_span_map([_analysis(status=ElementStatus.UNCLEAR)])

    entry = support_map.entries[0]
    assert entry.support_status == "needs_review"
    assert entry.review_required is True
    assert support_map.unsupported_customer_visible_claim_count == 0
    assert support_map.needs_review_count == 1


def test_claim_source_span_map_unclear_elements_with_evidence_still_need_review() -> None:
    support_map = build_claim_source_span_map(
        [
            _analysis(
                status=ElementStatus.UNCLEAR,
                evidence="Spec discusses both alternatives",
                spec_citation="col. 5, lines 1-7",
            )
        ]
    )

    entry = support_map.entries[0]
    assert entry.support_status == "needs_review"
    assert entry.review_required is True
    assert entry.source_span_ids
    assert support_map.unsupported_customer_visible_claim_count == 0
    assert support_map.needs_review_count == 1


def test_claim_source_span_map_is_deterministic() -> None:
    first = build_claim_source_span_map([_analysis(evidence="Example 3 discloses X")])
    second = build_claim_source_span_map([_analysis(evidence="Example 3 discloses X")])

    assert first == second


def test_unsupported_customer_visible_claims_gate_still_active() -> None:
    # The fail-closed gate should never trigger for normal pipeline output because
    # build_claim_source_span_map now maps missing evidence to "needs_review".
    # But the gate must still reject any "unsupported" entry that could arrive
    # via other code paths (defensive).
    import uuid

    from praviar_pipeline.models.report_source_spans import (
        ClaimAssertionSupport,
        ClaimSourceSpanMap,
    )

    bad_entry = ClaimAssertionSupport(
        assertion_id=str(uuid.uuid4()),
        patent_id="US1234567B2",
        claim_number=1,
        element_number=1,
        report_section="claim_element_analysis",
        assertion_text="Claim 1 element 1 was assessed as met.",
        source_span_ids=[],
        support_status="unsupported",
        customer_visible=True,
    )
    bad_map = ClaimSourceSpanMap(
        entries=[bad_entry],
        spans={},
        unsupported_customer_visible_claim_count=1,
        needs_review_count=0,
    )

    try:
        ensure_no_unsupported_customer_visible_claims(bad_map)
    except UnsupportedCustomerVisibleClaimError as exc:
        assert exc.assertion_ids == [bad_entry.assertion_id]
    else:
        raise AssertionError("unsupported customer-visible assertion was not rejected")


def test_normal_pipeline_output_does_not_trigger_fail_closed_gate() -> None:
    # An element with a determination but no evidence maps to needs_review, not
    # unsupported, so the fail-closed gate should pass cleanly.
    support_map = build_claim_source_span_map([_analysis()])
    ensure_no_unsupported_customer_visible_claims(support_map)  # must not raise


def test_missing_high_risk_claim_coverage_fails_closed() -> None:
    support_map = build_claim_source_span_map(
        [
            SimpleNamespace(
                patent_id="US-BLOCKER",
                risk_level=RiskLevel.HIGH,
                claims_analyzed=[],
            )
        ]
    )

    assert support_map.unsupported_customer_visible_claim_count == 1
    assert support_map.entries[0].report_section == "claim_source_span_coverage"
    try:
        ensure_no_unsupported_customer_visible_claims(support_map)
    except UnsupportedCustomerVisibleClaimError as exc:
        assert exc.assertion_ids == [support_map.entries[0].assertion_id]
    else:
        raise AssertionError("missing high-risk claim coverage was not rejected")


def test_missing_high_risk_claim_elements_fail_closed() -> None:
    support_map = build_claim_source_span_map(
        [
            SimpleNamespace(
                patent_id="US-BLOCKER",
                risk_level=RiskLevel.HIGH,
                claims_analyzed=[SimpleNamespace(claim_number=1, elements=[])],
            )
        ]
    )

    assert support_map.unsupported_customer_visible_claim_count == 1
    assert support_map.entries[0].claim_number == 1
    try:
        ensure_no_unsupported_customer_visible_claims(support_map)
    except UnsupportedCustomerVisibleClaimError as exc:
        assert exc.assertion_ids == [support_map.entries[0].assertion_id]
    else:
        raise AssertionError("missing high-risk claim elements were not rejected")


def test_supported_customer_visible_claims_pass_enforcement() -> None:
    support_map = build_claim_source_span_map(
        [_analysis(evidence="Example 3 discloses X", spec_citation="col. 5, lines 1-7")],
        _patent_details(),
    )

    ensure_no_unsupported_customer_visible_claims(support_map)

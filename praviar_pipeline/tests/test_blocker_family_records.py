from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from praviar_pipeline.models.report import (
    BlockerClaimRecord,
    BlockerFamilyRecord,
    ClaimProgramSummary,
    ClearanceDecisionAudit,
    ClearanceOutcome,
)
from praviar_pipeline.models.report_decisioning_core import blocker_family_record_id
from praviar_pipeline.pipeline.report.blocker_family_records import (
    build_blocker_family_records,
)


def _decision(patent_id: str, claim_number: int, jurisdiction: str):
    return SimpleNamespace(
        patent_id=patent_id,
        claim_number=claim_number,
        jurisdiction=jurisdiction,
        literal_risk="high",
        doe_risk="low",
        invalidity_strength="weak",
        legal_status="active",
        legal_status_provenance_verified=True,
        prospective_enforceability="active",
        accused_acts=["make", "sell"],
        accused_acts_verified=True,
        evidence_sufficient=True,
        record_basis=["verified_claim_text", "verified_legal_status"],
    )


def _substrate():
    summary = ClaimProgramSummary(
        blocking_claim_ids=["US123B2#claim1", "EP456B1#claim4"],
        blocking_patent_ids=["US123B2", "EP456B1"],
    )
    decisions = [
        _decision("US123B2", 1, "US"),
        _decision("EP456B1", 4, "EP"),
    ]
    evidence_index = SimpleNamespace(
        patent_records=[
            SimpleNamespace(patent_id="US123B2", family_id="fam-acme-1"),
            SimpleNamespace(patent_id="EP456B1", family_id="fam-acme-1"),
        ],
        family_records=[
            SimpleNamespace(
                family_id="fam-acme-1",
                material_patent_ids=["US123B2", "EP456B1", "WO789A1"],
            )
        ],
    )
    return summary, decisions, evidence_index


def test_builds_one_exact_record_per_governed_blocking_family() -> None:
    summary, decisions, evidence_index = _substrate()

    records = build_blocker_family_records(
        decision=ClearanceOutcome.BLOCKED,
        claim_program_summary=summary,
        claim_program_decisions=decisions,
        matter_evidence_index=evidence_index,
    )

    assert len(records) == 1
    record = records[0]
    assert record.schema_version == "blocker-family-v1"
    assert record.blocker_id == "bf_2f994b95f175a8ef"
    assert record.family_id == "fam-acme-1"
    assert record.primary_blocking_patent_id == "EP456B1"
    assert record.material_family_patent_ids == [
        "EP456B1",
        "US123B2",
        "WO789A1",
    ]
    assert record.blocking_patent_ids == ["EP456B1", "US123B2"]
    assert record.jurisdictions == ["EP", "US"]
    assert [claim.claim_id for claim in record.blocking_claims] == [
        "EP456B1#claim4",
        "US123B2#claim1",
    ]
    assert all(claim.evidence_sufficient for claim in record.blocking_claims)
    assert all(claim.legal_status_provenance_verified for claim in record.blocking_claims)
    assert all(claim.accused_acts_verified for claim in record.blocking_claims)


def test_output_is_identical_when_input_order_changes() -> None:
    summary, decisions, evidence_index = _substrate()
    first = build_blocker_family_records(
        decision=ClearanceOutcome.BLOCKED,
        claim_program_summary=summary,
        claim_program_decisions=decisions,
        matter_evidence_index=evidence_index,
    )
    shuffled_summary = summary.model_copy(
        update={
            "blocking_claim_ids": list(reversed(summary.blocking_claim_ids)),
            "blocking_patent_ids": list(reversed(summary.blocking_patent_ids)),
        }
    )
    evidence_index.patent_records.reverse()
    evidence_index.family_records[0].material_patent_ids.reverse()
    second = build_blocker_family_records(
        decision=ClearanceOutcome.BLOCKED,
        claim_program_summary=shuffled_summary,
        claim_program_decisions=list(reversed(decisions)),
        matter_evidence_index=evidence_index,
    )

    assert [record.model_dump() for record in first] == [record.model_dump() for record in second]


def test_missing_authoritative_family_membership_fails_closed() -> None:
    summary, decisions, evidence_index = _substrate()
    evidence_index.patent_records[0].family_id = ""

    with pytest.raises(ValueError, match="family membership"):
        build_blocker_family_records(
            decision=ClearanceOutcome.BLOCKED,
            claim_program_summary=summary,
            claim_program_decisions=decisions,
            matter_evidence_index=evidence_index,
        )


@pytest.mark.parametrize("duplicate_kind", ["patent", "family"])
def test_duplicate_evidence_mappings_fail_closed(duplicate_kind: str) -> None:
    summary, decisions, evidence_index = _substrate()
    if duplicate_kind == "patent":
        evidence_index.patent_records.append(
            SimpleNamespace(patent_id="US123B2", family_id="different-family")
        )
        expected_message = "duplicate patent record"
    else:
        evidence_index.family_records.append(
            SimpleNamespace(
                family_id="fam-acme-1",
                material_patent_ids=["US123B2"],
            )
        )
        expected_message = "duplicate family record"

    with pytest.raises(ValueError, match=expected_message):
        build_blocker_family_records(
            decision=ClearanceOutcome.BLOCKED,
            claim_program_summary=summary,
            claim_program_decisions=decisions,
            matter_evidence_index=evidence_index,
        )


def test_claim_zero_and_strong_invalidity_cannot_be_blockers() -> None:
    summary, decisions, evidence_index = _substrate()
    summary.blocking_claim_ids[0] = "US123B2#claim0"
    with pytest.raises(ValueError, match="invalid governed blocking claim"):
        build_blocker_family_records(
            decision=ClearanceOutcome.BLOCKED,
            claim_program_summary=summary,
            claim_program_decisions=decisions,
            matter_evidence_index=evidence_index,
        )

    summary, decisions, evidence_index = _substrate()
    decisions[0].invalidity_strength = "strong"
    with pytest.raises(ValidationError, match="strong-invalidity"):
        build_blocker_family_records(
            decision=ClearanceOutcome.BLOCKED,
            claim_program_summary=summary,
            claim_program_decisions=decisions,
            matter_evidence_index=evidence_index,
        )


def test_non_blocked_decision_has_no_blocker_family_records() -> None:
    summary, decisions, evidence_index = _substrate()

    assert (
        build_blocker_family_records(
            decision=ClearanceOutcome.UNCLEAR,
            claim_program_summary=summary,
            claim_program_decisions=decisions,
            matter_evidence_index=evidence_index,
        )
        == []
    )


def test_blocker_claim_requires_high_risk_active_status_and_canonical_evidence_lists() -> None:
    claim_payload = {
        "claim_id": "US123B2#claim1",
        "patent_id": "US123B2",
        "claim_number": 1,
        "jurisdiction": "US",
        "literal_risk": "low",
        "doe_risk": "low",
        "invalidity_strength": "weak",
        "legal_status": "active",
        "legal_status_provenance_verified": True,
        "prospective_enforceability": "active",
        "accused_acts": ["make"],
        "accused_acts_verified": True,
        "evidence_sufficient": True,
        "record_basis": ["verified_claim_text"],
    }
    with pytest.raises(ValidationError, match="high literal or equivalents"):
        BlockerClaimRecord(**claim_payload)

    claim_payload["literal_risk"] = "high"
    claim_payload["legal_status"] = "expired"
    with pytest.raises(ValidationError, match="legal_status"):
        BlockerClaimRecord(**claim_payload)

    claim_payload["legal_status"] = "active"
    claim_payload["accused_acts"] = ["sell", "make"]
    with pytest.raises(ValidationError, match="accused acts must be sorted and unique"):
        BlockerClaimRecord(**claim_payload)

    claim_payload["accused_acts"] = ["make"]
    claim_payload["record_basis"] = [""]
    with pytest.raises(ValidationError, match=r"record basis.*nonblank"):
        BlockerClaimRecord(**claim_payload)


def test_blocker_family_requires_hash_and_exact_claim_jurisdictions() -> None:
    claim = BlockerClaimRecord(
        claim_id="US123B2#claim1",
        patent_id="US123B2",
        claim_number=1,
        jurisdiction="US",
        literal_risk="high",
        legal_status="active",
        legal_status_provenance_verified=True,
        prospective_enforceability="active",
        accused_acts=["make"],
        accused_acts_verified=True,
        evidence_sufficient=True,
        record_basis=["verified_claim_text"],
    )
    family_payload = {
        "blocker_id": "bf_0123456789abcdef",
        "family_id": "fam-1",
        "primary_blocking_patent_id": "US123B2",
        "material_family_patent_ids": ["US123B2"],
        "blocking_patent_ids": ["US123B2"],
        "jurisdictions": ["US"],
        "blocking_claims": [claim],
    }
    with pytest.raises(ValidationError, match="canonical family identity"):
        BlockerFamilyRecord(**family_payload)

    family_payload["blocker_id"] = blocker_family_record_id("fam-1")
    family_payload["jurisdictions"] = ["EP"]
    with pytest.raises(ValidationError, match="exactly match its blocking claims"):
        BlockerFamilyRecord(**family_payload)


def test_blocking_summary_requires_canonical_family_records() -> None:
    with pytest.raises(ValidationError, match="summaries require canonical blocker families"):
        ClearanceDecisionAudit(
            claim_program_summary=ClaimProgramSummary(
                blocking_claim_ids=["US123B2#claim1"],
                blocking_patent_ids=["US123B2"],
            )
        )


def test_audit_rejects_tampered_blocker_projection() -> None:
    claim = BlockerClaimRecord(
        claim_id="US123B2#claim1",
        patent_id="US123B2",
        claim_number=1,
        jurisdiction="US",
        literal_risk="high",
        doe_risk="low",
        invalidity_strength="weak",
        legal_status="active",
        legal_status_provenance_verified=True,
        prospective_enforceability="active",
        accused_acts=["make"],
        accused_acts_verified=True,
        evidence_sufficient=True,
        record_basis=["verified_claim_text"],
    )
    family = BlockerFamilyRecord(
        blocker_id=blocker_family_record_id("fam-1"),
        family_id="fam-1",
        primary_blocking_patent_id="US123B2",
        material_family_patent_ids=["US123B2"],
        blocking_patent_ids=["US123B2"],
        jurisdictions=["US"],
        blocking_claims=[claim],
    )

    with pytest.raises(ValidationError, match="exactly cover blocking claim"):
        ClearanceDecisionAudit(
            claim_program_summary=ClaimProgramSummary(
                blocking_claim_ids=["US123B2#claim2"],
                blocking_patent_ids=["US123B2"],
            ),
            blocker_families=[family],
        )

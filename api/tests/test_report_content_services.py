"""Tests for report content service helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from certification_keyring_fixtures import (
    TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
    TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET,
)
from conftest import valid_report_data, valid_report_data_for_patents
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from praviar_pipeline.certification_receipt import PAYLOAD_TYPE, canonical_json_bytes
from praviar_pipeline.certification_subject import compute_certification_bundle_digests
from praviar_pipeline.checkpoint import (
    DEV_CHECKPOINT_HMAC_KEYRING_SECRET,
    CheckpointIntegrityKeyRing,
)
from praviar_pipeline.models.report_source_spans import (
    build_claim_source_span_map,  # type: ignore[import-not-found]
)
from praviar_pipeline.report_certification_binding import (
    ReportCertificationSigner,
    sign_report_certification_binding,
)
from pydantic import SecretStr

from api.db.models import AnalysisStatus
from api.errors import APIError
from api.services.report_access import (
    build_governed_report_summary,
    report_payload_fingerprint,
    require_completed_report_payload,
    validate_claim_source_span_map,
    validate_report_publishability,
)
from api.services.report_content import (
    filter_risk_ratings,
    get_report_summary_for_org,
    load_report_for_org,
    search_report_content,
)


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _authorized_report_query_results(
    analysis_id: uuid.UUID,
    *,
    org_id: uuid.UUID | None = None,
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
    has_report_data: bool = True,
    report_data: dict | None = None,
) -> list[MagicMock]:
    resolved_report_data = report_data or valid_report_data()
    if org_id is not None:
        resolved_report_data["report_certification_binding"] = sign_report_certification_binding(
            resolved_report_data,
            signer=ReportCertificationSigner.from_secret(
                TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
            ),
            analysis_id=str(analysis_id),
            org_id=str(org_id),
        )
    return [
        _scalar_result(status),
        _scalar_result(resolved_report_data if has_report_data else None),
    ]


def _searchable_report() -> dict:
    return valid_report_data(
        patent_analyses=[
            {
                "patent_id": "US12345678A1",
                "title": "Novel aspirin formulation",
                "risk_summary": "High risk due to scaffold overlap.",
            }
        ],
        risk_summary={
            "overall_risk": "medium",
            "blocking_patents_count": 1,
            "total_patents_analyzed": 1,
            "key_risks": ["Scaffold overlap"],
            "executive_summary": "Moderate risk due to aspirin coverage.",
        },
        doe_assessments=[
            {
                "patent_id": "US12345678A1",
                "reasoning": "Equivalents analysis shows possible coverage.",
            }
        ],
        invalidity_assessments=[
            {
                "patent_id": "US12345678A1",
                "reasoning": "Prior art may invalidate claim 1.",
            }
        ],
        action_items=["Talk to counsel"],
    )


def test_filter_risk_ratings_redacts_legal_conclusions():
    filtered = filter_risk_ratings(_searchable_report())

    assert filtered["risk_summary"]["overall_risk"] is None
    assert filtered["risk_summary"]["blocking_patents_count"] is None
    assert filtered["risk_summary"]["key_risks"] == []


def test_validate_claim_source_span_map_rejects_malformed_span_objects():
    support_map = valid_report_data()["claim_source_span_map"]
    support_map["spans"]["span-test-1"].pop("source_type")

    with pytest.raises(ValueError, match="schema validation"):
        validate_claim_source_span_map(support_map)


def test_validate_claim_source_span_map_rejects_malformed_support_entries():
    support_map = valid_report_data()["claim_source_span_map"]
    support_map["entries"][0].pop("report_section")

    with pytest.raises(ValueError, match="schema validation"):
        validate_claim_source_span_map(support_map)


def test_validate_claim_source_span_map_rejects_stale_needs_review_count():
    support_map = valid_report_data()["claim_source_span_map"]
    support_map["entries"].append(
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
    )
    support_map["needs_review_count"] = 0

    with pytest.raises(ValueError, match="needs_review_count must match entries"):
        validate_claim_source_span_map(support_map)


def test_validate_claim_source_span_map_rejects_string_customer_visible_flag():
    support_map = valid_report_data()["claim_source_span_map"]
    entry = support_map["entries"][0]
    entry["support_status"] = "unsupported"
    entry["source_span_ids"] = []
    entry["customer_visible"] = "false"
    support_map["unsupported_customer_visible_claim_count"] = 0

    with pytest.raises(ValueError, match="schema validation"):
        validate_claim_source_span_map(support_map)


def test_validate_claim_source_span_map_rejects_mismatched_empty_source_span():
    support_map = valid_report_data()["claim_source_span_map"]
    entry = support_map["entries"][0]
    entry["patent_id"] = "US91000021A1"
    entry["claim_number"] = 1
    entry["element_number"] = 1
    entry["source_span_ids"] = ["borrowed-span"]
    support_map["spans"] = {
        "borrowed-span": {
            "span_id": "different-embedded-id",
            "source_type": "element_evidence",
            "patent_id": "US91000022A1",
            "claim_number": 99,
            "element_number": 9,
            "citation": "",
            "excerpt": "",
        }
    }

    with pytest.raises(ValueError, match="source span"):
        validate_claim_source_span_map(support_map)


def test_validate_claim_source_span_map_rejects_reasoning_only_supported_claim():
    support_map = deepcopy(valid_report_data()["claim_source_span_map"])
    entry = support_map["entries"][0]
    entry["source_span_ids"] = ["reasoning-span"]
    support_map["spans"] = {
        "reasoning-span": {
            "span_id": "reasoning-span",
            "source_type": "claim_reasoning",
            "patent_id": entry["patent_id"],
            "claim_number": entry["claim_number"],
            "element_number": entry["element_number"],
            "citation": "",
            "excerpt": "Generated reasoning cannot be the only support for a claim.",
        }
    }

    with pytest.raises(ValueError, match="evidence-grade source spans"):
        validate_claim_source_span_map(support_map)


def test_validate_report_publishability_rejects_forged_verified_claim_span():
    report = deepcopy(valid_report_data())
    report["claim_source_span_map"]["spans"]["span-test-1"]["source_text_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="invalid artifact-grade provenance"):
        validate_report_publishability(report)


@pytest.mark.parametrize(
    "field_name",
    [
        "source_document_id",
        "source_name",
        "source_text_sha256",
        "source_retrieved_at",
        "source_artifact_locator",
        "collector_identity",
        "collector_version",
        "provenance_cassette_sha256",
    ],
)
def test_verified_claim_span_requires_every_artifact_grade_field(field_name: str):
    report = deepcopy(valid_report_data())
    report["claim_source_span_map"]["spans"]["span-test-1"][field_name] = ""

    with pytest.raises(ValueError, match="complete artifact-grade provenance"):
        validate_report_publishability(report)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("source_text_sha256", "0" * 64),
        (
            "source_artifact_locator",
            f"https://attacker.invalid/claim#sha256={'0' * 64}",
        ),
        ("provenance_cassette_sha256", "f" * 64),
    ],
)
def test_verified_claim_span_revalidates_hash_locator_and_cassette(
    field_name: str,
    replacement: str,
):
    report = deepcopy(valid_report_data())
    report["claim_source_span_map"]["spans"]["span-test-1"][field_name] = replacement

    with pytest.raises(ValueError, match="invalid artifact-grade provenance"):
        validate_report_publishability(report)


def test_verified_claim_span_must_match_patent_detail_cassette():
    report = deepcopy(valid_report_data())
    provenance = report["patent_details"]["US12345678A1"]["claims_text_provenance"]
    provenance["collector_identity"] = "forged.detail.collector"

    with pytest.raises(ValueError, match="invalid artifact-grade provenance"):
        validate_report_publishability(report)


def test_require_completed_report_payload_rejects_empty_source_span_map():
    report = valid_report_data(
        patent_analyses=[
            {
                "patent_id": "US12345678A1",
                "title": "Customer-visible patent analysis",
                "risk_summary": "Risk language requires source-span support.",
            }
        ],
        claim_source_span_map={
            "generated_from": "empty_test_map",
            "entries": [],
            "spans": {},
            "unsupported_customer_visible_claim_count": 0,
            "needs_review_count": 0,
        },
    )
    analysis = MagicMock(
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )

    with pytest.raises(APIError) as exc_info:
        require_completed_report_payload(analysis)

    assert exc_info.value.status == 404


def test_unclear_completed_report_is_bound_to_its_analysis_and_organization() -> None:
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = valid_report_data()
    report["report_certification_binding"] = sign_report_certification_binding(
        report,
        signer=ReportCertificationSigner.from_secret(
            TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
        ),
        analysis_id=str(analysis_id),
        org_id=str(org_id),
    )
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )

    assert require_completed_report_payload(analysis) is report

    analysis.id = uuid.uuid4()
    analysis.org_id = uuid.uuid4()
    with pytest.raises(APIError) as exc_info:
        require_completed_report_payload(analysis)
    assert exc_info.value.status == 404


def test_completed_no_patent_report_without_independent_zero_search_contract_is_rejected():
    report = valid_report_data(
        patent_analyses=[],
        total_patents_found=0,
        risk_summary={
            "overall_risk": "clear",
            "blocking_patents_count": 0,
            "total_patents_analyzed": 0,
            "key_risks": [],
            "executive_summary": (
                "Clearance decision: CLEAR. 0 blocking patents identified from 0 analyzed."
            ),
        },
        claim_source_span_map=build_claim_source_span_map([]).model_dump(mode="json"),
        analysis_failures=[],
    )
    decision_audit = report["clearance_decision"]["decision_audit"]
    report["clearance_decision"]["decision"] = "clear"
    decision_audit["evidence_sufficient_for_clearance"] = True
    decision_audit["analysis_failures_count"] = 0
    decision_audit["material_patents_reviewed"] = 0
    decision_audit["material_us_patents"] = 0
    decision_audit["material_ep_patents"] = 0
    decision_audit["patents_with_claims"] = 0
    decision_audit["patents_with_family"] = 0
    decision_audit["us_patents_with_prosecution_context"] = 0
    decision_audit["us_patents_with_file_wrapper_dossier"] = 0
    decision_audit["ep_patents_with_register_context"] = 0
    decision_audit["clearance_grade_ready_patents"] = 0
    decision_audit["incomplete_material_patents"] = 0
    decision_audit["clearance_grade_ready_families"] = 0
    decision_audit["incomplete_material_families"] = 0
    decision_audit["failed_sources"] = []
    decision_audit["decisive_references"] = []
    claim_program = decision_audit["claim_program_summary"]
    for field in (
        "blocking_claim_ids",
        "contested_claim_ids",
        "medium_risk_claim_ids",
        "claims_with_strong_invalidity",
        "claims_with_insufficient_evidence",
        "blocking_patent_ids",
        "contested_patent_ids",
        "medium_risk_patent_ids",
    ):
        claim_program[field] = []
    claim_program["total_claim_programs_reviewed"] = 0
    claim_program["patent_level_fallback_count"] = 0
    report["claim_program_decisions"] = []
    coverage = decision_audit["coverage_summary"]
    for field in (
        "failed_source_names",
        "reviewed_patent_ids",
        "reviewed_us_patent_ids",
        "reviewed_ep_patent_ids",
        "patents_missing_claims",
        "patents_missing_claim_level_analysis",
        "patents_missing_authoritative_records",
        "patents_missing_family_context",
        "failed_analysis_patent_ids",
        "clearance_grade_ready_patent_ids",
        "incomplete_patent_ids",
        "clearance_grade_ready_family_ids",
        "incomplete_family_ids",
        "verification_gaps",
    ):
        coverage[field] = []
    for source in report["source_health"]["entries"]:
        if source["status"] == "failed":
            source["status"] = "skipped"
    report["jurisdiction_decisions"] = []
    report["evidence_artifacts"] = []
    report["prosecution_dossiers"] = []
    report["matter_evidence_index"]["patent_records"] = []
    report["matter_evidence_index"]["family_records"] = []
    report["patents_after_triage"] = 0
    report["audit_trail"].update(
        {
            "total_patents_discovered": 0,
            "patents_after_hard_filter": 0,
            "patents_after_ranking": 0,
            "patents_after_triage": 0,
            "patents_analyzed": 0,
        }
    )
    analysis = MagicMock(
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )

    with pytest.raises(APIError) as exc_info:
        require_completed_report_payload(analysis)

    assert exc_info.value.status == 404


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda report: report["risk_summary"].update({"overall_risk": "high"}),
            "overall_risk",
        ),
        (
            lambda report: report["risk_summary"].update({"blocking_patents_count": 1}),
            "blocking_patents_count",
        ),
        (
            lambda report: report["risk_summary"].update({"executive_summary": "drifted"}),
            "governed summary",
        ),
        (
            lambda report: report["clearance_decision"]["decision_audit"].update(
                {"material_patents_reviewed": 99}
            ),
            "material_patents_reviewed",
        ),
        (
            lambda report: report["jurisdiction_decisions"][0].update(
                {"blocking_patent_ids": ["US12345678A1"]}
            ),
            "blocking IDs",
        ),
        (
            lambda report: report["clearance_decision"]["decision_audit"][
                "claim_program_summary"
            ].update({"medium_risk_patent_ids": []}),
            "medium_risk_patent_ids",
        ),
        (
            lambda report: report["clearance_decision"]["decision_audit"].update(
                {"evidence_sufficient_for_clearance": True}
            ),
            "evidence sufficiency",
        ),
    ],
)
def test_report_publishability_rejects_semantic_drift(mutation, message: str):
    report = deepcopy(valid_report_data())
    mutation(report)

    with pytest.raises(ValueError, match=message):
        validate_report_publishability(report)


def test_report_publishability_rejects_blocked_decision_with_zero_blockers():
    report = deepcopy(valid_report_data())
    report["clearance_decision"]["decision"] = "blocked"
    report["jurisdiction_decisions"][0]["decision"] = "blocked"
    report["risk_summary"].update(
        {
            "overall_risk": "high",
            "blocking_patents_count": 0,
            "executive_summary": (
                "Clearance decision: BLOCKED. 0 blocking patents identified from 1 analyzed."
            ),
        }
    )

    with pytest.raises(ValueError, match="zero blockers"):
        validate_report_publishability(report)


def test_report_publishability_rejects_analysis_risk_blocker_set_drift():
    report = valid_report_data_for_patents(
        [
            {"patent_id": "US11111111A1", "risk_level": "high", "risk_summary": "high"},
            {"patent_id": "US22222222A1", "risk_level": "high", "risk_summary": "high"},
        ]
    )
    report["patent_analyses"][1]["risk_level"] = "clear"

    with pytest.raises(ValueError, match="high-risk IDs"):
        validate_report_publishability(report)


def test_report_publishability_rejects_coordinated_jurisdiction_label_drift():
    report = deepcopy(valid_report_data())
    report["jurisdiction_decisions"][0]["jurisdiction"] = "CN"

    with pytest.raises(ValueError, match="reviewed IDs do not match patent IDs"):
        validate_report_publishability(report)


def test_report_publishability_rejects_coordinated_us_ep_coverage_drift():
    report = deepcopy(valid_report_data())
    audit = report["clearance_decision"]["decision_audit"]
    coverage = audit["coverage_summary"]
    coverage["reviewed_us_patent_ids"] = []
    coverage["reviewed_ep_patent_ids"] = ["US12345678A1"]
    audit["material_us_patents"] = 0
    audit["material_ep_patents"] = 1

    with pytest.raises(ValueError, match="reviewed_us_patent_ids"):
        validate_report_publishability(report)


def test_report_publishability_rejects_coordinated_analyzed_count_drift():
    report = deepcopy(valid_report_data())
    report["risk_summary"]["total_patents_analyzed"] = 999
    report["risk_summary"]["executive_summary"] = (
        "Clearance decision: UNCLEAR. 0 blocking patents identified from 999 analyzed."
    )

    with pytest.raises(ValueError, match="total_patents_analyzed"):
        validate_report_publishability(report)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("audit", "patents_with_claims"),
        ("audit", "patents_with_family"),
        ("audit", "us_patents_with_prosecution_context"),
        ("audit", "ep_patents_with_register_context"),
        ("claim_program", "total_claim_programs_reviewed"),
        ("claim_program", "patent_level_fallback_count"),
    ],
)
def test_report_publishability_rejects_derived_count_drift(section: str, field: str):
    report = deepcopy(valid_report_data())
    audit = report["clearance_decision"]["decision_audit"]
    target = audit if section == "audit" else audit["claim_program_summary"]
    target[field] = 999

    with pytest.raises(ValueError, match=field):
        validate_report_publishability(report)


def test_report_publishability_rejects_search_funnel_count_drift():
    report = deepcopy(valid_report_data())
    report["total_patents_found"] = 0
    report["patents_after_triage"] = 0

    with pytest.raises(ValueError, match="total_patents_found|patents_after_triage"):
        validate_report_publishability(report)


def test_report_publishability_requires_decisive_reference_for_every_blocker():
    report = valid_report_data_for_patents(
        [
            {"patent_id": "US11111111A1", "risk_level": "high", "risk_summary": "high"},
            {"patent_id": "US22222222A1", "risk_level": "high", "risk_summary": "high"},
        ]
    )
    report["clearance_decision"]["decision_audit"]["decisive_references"].pop()

    with pytest.raises(ValueError, match="decisive blocker references"):
        validate_report_publishability(report)


def test_report_publishability_rejects_clear_outside_certified_decision_scope():
    report = _semantic_clear_report()
    report["decision_scope"].update({"jurisdictions": [], "supports_positive_clearance": False})
    report["supporting_scope"]["jurisdictions"] = ["US"]
    report["certification_scope"].update(
        {
            "certified_jurisdictions": [],
            "supporting_only_jurisdictions": ["US"],
            "current_matter_type_certified": False,
            "attorney_supervision_required": True,
        }
    )
    report["cohort_status"] = "supporting_only"

    with pytest.raises(ValueError, match="certified cohort|decision scope"):
        validate_report_publishability(report)


def test_report_publishability_accepts_all_decisive_references_for_many_blockers():
    report = valid_report_data_for_patents(
        [
            {
                "patent_id": f"US{index:08d}A1",
                "risk_level": "high",
                "risk_summary": "high",
            }
            for index in range(1, 6)
        ]
    )

    assert validate_report_publishability(report)["blocking_patent_count"] == 5


def test_report_publishability_accepts_mixed_claim_risk_with_patent_precedence():
    patent_id = "US12345678A1"
    report = valid_report_data_for_patents(
        [{"patent_id": patent_id, "risk_level": "high", "risk_summary": "high"}]
    )
    report["claim_program_decisions"] = [
        {
            "patent_id": patent_id,
            "claim_number": 1,
            "literal_risk": "high",
            "doe_risk": "not_assessed",
            "invalidity_strength": "strong",
            "evidence_sufficient": True,
        },
        {
            "patent_id": patent_id,
            "claim_number": 2,
            "literal_risk": "high",
            "doe_risk": "not_assessed",
            "invalidity_strength": "",
            "evidence_sufficient": True,
        },
    ]
    claim_program = report["clearance_decision"]["decision_audit"]["claim_program_summary"]
    claim_program.update(
        {
            "total_claim_programs_reviewed": 2,
            "blocking_claim_ids": [f"{patent_id}#claim2"],
            "contested_claim_ids": [f"{patent_id}#claim1"],
            "medium_risk_claim_ids": [],
            "claims_with_strong_invalidity": [f"{patent_id}#claim1"],
            "claims_with_insufficient_evidence": [],
            "blocking_patent_ids": [patent_id],
            "contested_patent_ids": [],
            "medium_risk_patent_ids": [],
        }
    )
    report["matter_store"]["claim_program_decisions"] = deepcopy(report["claim_program_decisions"])

    assert validate_report_publishability(report)["blocking_patent_count"] == 1


def test_report_publishability_derives_counts_from_unique_canonical_rows():
    report = deepcopy(valid_report_data())
    report["analysis_failures"] *= 999
    report["claim_program_decisions"] *= 999
    audit = report["clearance_decision"]["decision_audit"]
    audit["claim_program_summary"]["total_claim_programs_reviewed"] = 1

    assert validate_report_publishability(report)["decision"] == "unclear"

    report["total_patents_found"] = 1000
    report["patents_after_triage"] = 1000
    report["audit_trail"].update(
        {
            "total_patents_discovered": 1000,
            "patents_after_hard_filter": 1000,
            "patents_after_ranking": 1000,
            "patents_after_triage": 1000,
        }
    )
    with pytest.raises(ValueError, match="analyses plus failures"):
        validate_report_publishability(report)


def test_report_publishability_rejects_contradictory_duplicate_claim_decisions():
    report = deepcopy(valid_report_data())
    duplicate = deepcopy(report["claim_program_decisions"][0])
    duplicate.update(literal_risk="high", evidence_sufficient=True)
    report["claim_program_decisions"].append(duplicate)

    with pytest.raises(ValueError, match="contradictory duplicate"):
        validate_report_publishability(report)


def test_report_publishability_rejects_negative_claim_identity():
    report = deepcopy(valid_report_data())
    report["claim_program_decisions"][0]["claim_number"] = -1

    with pytest.raises(ValueError, match="cannot be negative"):
        validate_report_publishability(report)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda report: report["commercial_exposure"].update(
                blocking_patent_ids=["US12345678A1"]
            ),
            "commercial_exposure blocker IDs",
        ),
        (
            lambda report: report["matter_store"]["claim_program_decisions"][0].update(
                literal_risk="high"
            ),
            "matter_store claim-program decisions",
        ),
        (
            lambda report: report["authority_coverage"].update(
                patents_with_authoritative_records=999
            ),
            "authority_coverage patents_with_authoritative_records",
        ),
    ],
)
def test_report_publishability_rejects_published_mirror_drift(mutate, message: str):
    report = deepcopy(valid_report_data())
    mutate(report)

    with pytest.raises(ValueError, match=message):
        validate_report_publishability(report)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda report: report.__setitem__("commercial_exposure", {}),
            "commercial_exposure is incomplete",
        ),
        (
            lambda report: report["matter_store"].__setitem__("claim_program_decisions", []),
            "matter_store claim-program decisions",
        ),
        (
            lambda report: report["matter_store"].__setitem__("authority_coverage", {}),
            "matter_store authority_coverage",
        ),
    ],
)
def test_report_publishability_rejects_empty_required_mirrors(mutate, message: str):
    report = deepcopy(valid_report_data())
    mutate(report)

    with pytest.raises(ValueError, match=message):
        validate_report_publishability(report)


def test_report_publishability_rejects_matter_store_missing_component_drift():
    report = deepcopy(valid_report_data())
    report["matter_store"]["claim_program_decisions"][0]["missing_components"] = ["invented_gap"]

    with pytest.raises(ValueError, match="matter_store claim-program decisions"):
        validate_report_publishability(report)


def test_report_publishability_rejects_coordinated_invented_authority_categories():
    report = deepcopy(valid_report_data())
    for authority in (
        report["authority_coverage"],
        report["matter_store"]["authority_coverage"],
    ):
        authority["authoritative_categories_covered"] = ["invented_category"]

    with pytest.raises(ValueError, match="covered categories"):
        validate_report_publishability(report)


@pytest.mark.parametrize("reverse", [False, True])
def test_report_publishability_rejects_whole_document_and_positive_claim_coexistence(
    reverse: bool,
):
    report = deepcopy(valid_report_data())
    whole_document = deepcopy(report["claim_program_decisions"][0])
    whole_document["claim_number"] = 0
    decisions = [whole_document, report["claim_program_decisions"][0]]
    if reverse:
        decisions.reverse()
    report["claim_program_decisions"] = decisions
    report["matter_store"]["claim_program_decisions"] = deepcopy(decisions)

    with pytest.raises(ValueError, match="fallback cannot coexist"):
        validate_report_publishability(report)


def test_report_publishability_counts_whole_document_only_as_fallback():
    report = deepcopy(valid_report_data())
    patent_id = report["claim_program_decisions"][0]["patent_id"]
    report["claim_program_decisions"][0]["claim_number"] = 0
    report["matter_store"]["claim_program_decisions"] = deepcopy(report["claim_program_decisions"])
    claim_program = report["clearance_decision"]["decision_audit"]["claim_program_summary"]
    claim_program.update(
        {
            "total_claim_programs_reviewed": 0,
            "patent_level_fallback_count": 1,
            "medium_risk_claim_ids": [patent_id],
            "claims_with_insufficient_evidence": [patent_id],
        }
    )

    assert validate_report_publishability(report)["decision"] == "unclear"


def _semantic_clear_report() -> dict:
    report = deepcopy(valid_report_data())
    report["clearance_decision"]["decision"] = "clear"
    audit = report["clearance_decision"]["decision_audit"]
    audit.update(
        {
            "analysis_failures_count": 0,
            "clearance_grade_ready_patents": 1,
            "incomplete_material_patents": 0,
            "clearance_grade_ready_families": 0,
            "incomplete_material_families": 0,
            "failed_sources": [],
            "evidence_sufficient_for_clearance": True,
            "insufficiency_reasons": [],
            "evidence_warnings": [],
        }
    )
    coverage = audit["coverage_summary"]
    for field in (
        "failed_source_names",
        "patents_missing_claims",
        "patents_missing_claim_level_analysis",
        "patents_missing_authoritative_records",
        "patents_missing_family_context",
        "failed_analysis_patent_ids",
        "incomplete_patent_ids",
        "clearance_grade_ready_family_ids",
        "incomplete_family_ids",
        "verification_gaps",
    ):
        coverage[field] = []
    coverage["clearance_grade_ready_patent_ids"] = ["US12345678A1"]
    claim_program = audit["claim_program_summary"]
    for field in (
        "blocking_claim_ids",
        "contested_claim_ids",
        "medium_risk_claim_ids",
        "claims_with_strong_invalidity",
        "claims_with_insufficient_evidence",
        "blocking_patent_ids",
        "contested_patent_ids",
        "medium_risk_patent_ids",
    ):
        claim_program[field] = []
    report["claim_program_decisions"][0].update(
        {
            "literal_risk": "clear",
            "evidence_sufficient": True,
        }
    )
    report["jurisdiction_decisions"][0].update(
        {
            "decision": "clear",
            "evidence_sufficient_for_clearance": True,
            "gate_failures": [],
            "blocking_patent_ids": [],
        }
    )
    report["risk_summary"].update(
        {
            "overall_risk": "clear",
            "blocking_patents_count": 0,
            "key_risks": [],
            "executive_summary": (
                "Clearance decision: CLEAR. 0 blocking patents identified from 1 analyzed."
            ),
        }
    )
    report["analysis_failures"] = []
    report["patents_after_triage"] = 1
    report["audit_trail"]["patents_after_triage"] = 1
    for source in report["source_health"]["entries"]:
        if source["status"] == "failed":
            source["status"] = "skipped"
    report["matter_store"]["claim_program_decisions"] = deepcopy(report["claim_program_decisions"])
    report["report_certification_binding"] = sign_report_certification_binding(
        report,
        signer=ReportCertificationSigner.from_secret(
            TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
        ),
        analysis_id="test-analysis-id",
        org_id="test-org-id",
    )
    return report


def _dsse_bound_clear_report(
    *,
    analysis_id: str = "test-analysis-id",
    org_id: str = "test-org-id",
) -> tuple[dict, SimpleNamespace]:
    report = _semantic_clear_report()
    private_key = Ed25519PrivateKey.generate()
    public_key = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    now = datetime.now(UTC).replace(microsecond=0)
    bundle_digests = compute_certification_bundle_digests()
    payload = {
        "schema_version": "praviar.release-certification.v2",
        "receipt_id": "test-release-receipt",
        "issuer": {
            "verifier_id": "test-release-verifier",
            "key_id": "test-release-key",
        },
        "subject": {
            "git_sha": "b" * 40,
            "source_tree_sha256": "c" * 64,
            "api_oci_image_digest": "sha256:" + "1" * 64,
            "worker_oci_image_digest": "sha256:" + "2" * 64,
            **bundle_digests,
        },
        "gate": {
            "result": "PASSED",
            "gate_schema_version": 2,
            "threshold_policy_sha256": "8" * 64,
            "benchmark_aggregate_sha256": "d" * 64,
            "benchmark_manifest_sha256": "9" * 64,
            "canonical_attempt_ledger_sha256": "a" * 64,
            "adjudication_manifest_sha256": "b" * 64,
            "gate_run_id": "test-gate-run",
        },
        "certified_lanes": [
            {
                "lane_id": "us-small-molecule-compound-adaptive-v1",
                "matter_type": "small_molecule",
                "asset_class": "compound",
                "jurisdiction": "US",
                "execution_profile": "adaptive",
                "decision_kind": "positive_clearance",
                "required_record_components_sha256": "e" * 64,
                "benchmark_population_sha256": "f" * 64,
                "eligible_independent_case_count": 598,
                "eligible_predicted_clear_case_count": 299,
                "eligible_non_clear_case_count": 299,
                "observed_false_clear_count": 0,
                "false_clear_confidence_level": "0.95",
                "false_clear_upper_bound": "0.01",
            }
        ],
        "validity": {
            "issued_at": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "not_before": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "expires_at": (now + timedelta(days=7)).isoformat().replace("+00:00", "Z"),
            "revocation_namespace": "test-release-certification",
        },
    }
    payload_bytes = canonical_json_bytes(payload)
    payload_type = PAYLOAD_TYPE.encode()
    pae = (
        b"DSSEv1 "
        + str(len(payload_type)).encode()
        + b" "
        + payload_type
        + b" "
        + str(len(payload_bytes)).encode()
        + b" "
        + payload_bytes
    )
    envelope = {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload_bytes).decode(),
        "signatures": [
            {
                "keyid": "test-release-key",
                "sig": base64.b64encode(private_key.sign(pae)).decode(),
            }
        ],
    }
    receipt_dsse = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    certification = report["certification_scope"]
    certification["evidence_receipt_dsse"] = receipt_dsse
    certification["evidence_receipt_sha256"] = hashlib.sha256(
        canonical_json_bytes(envelope)
    ).hexdigest()
    certification["evidence_expires_at"] = payload["validity"]["expires_at"]
    report["report_certification_binding"] = sign_report_certification_binding(
        report,
        signer=ReportCertificationSigner.from_secret(
            TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
        ),
        analysis_id=analysis_id,
        org_id=org_id,
    )
    settings = SimpleNamespace(
        checkpoint_integrity_keys=CheckpointIntegrityKeyRing.from_secret(
            DEV_CHECKPOINT_HMAC_KEYRING_SECRET
        ),
        report_certification_public_keyring=TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
        certification_release_public_key=SecretStr(public_key),
        certification_release_key_id="test-release-key",
        certification_release_verifier_id="test-release-verifier",
        certification_api_oci_image_digest=payload["subject"]["api_oci_image_digest"],
        certification_worker_oci_image_digest=payload["subject"]["worker_oci_image_digest"],
        certification_runtime_policy_sha256=payload["subject"]["runtime_policy_sha256"],
        certification_evidence_policy_sha256=payload["subject"]["evidence_policy_sha256"],
        certification_prompt_bundle_sha256=payload["subject"]["prompt_bundle_sha256"],
        certification_model_bundle_sha256=payload["subject"]["model_bundle_sha256"],
        certification_tool_definition_bundle_sha256=payload["subject"][
            "tool_definition_bundle_sha256"
        ],
        certification_collector_bundle_sha256=payload["subject"]["collector_bundle_sha256"],
        certification_revoked_receipt_ids=(),
    )
    return report, settings


def _completed_clear_analysis(report: dict, *, analysis_id: str, org_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )


def test_completed_clear_report_reverifies_dsse_at_access() -> None:
    report, settings = _dsse_bound_clear_report()
    analysis = _completed_clear_analysis(
        report,
        analysis_id="test-analysis-id",
        org_id="test-org-id",
    )
    with (
        patch("api.services.report_access.get_settings", return_value=settings),
        patch(
            "praviar_pipeline.certification_receipt.get_pipeline_version",
            return_value="b" * 40,
        ),
        patch(
            "praviar_pipeline.certification_receipt.compute_source_tree_provenance",
            return_value=("build", "c" * 64),
        ),
    ):
        assert require_completed_report_payload(analysis) is report


def test_completed_historical_clear_report_survives_runtime_rollover() -> None:
    report, settings = _dsse_bound_clear_report()
    settings.certification_api_oci_image_digest = "sha256:" + "3" * 64
    settings.certification_worker_oci_image_digest = "sha256:" + "4" * 64
    settings.certification_runtime_policy_sha256 = "3" * 64
    settings.certification_evidence_policy_sha256 = "4" * 64
    settings.certification_prompt_bundle_sha256 = "5" * 64
    settings.certification_model_bundle_sha256 = "6" * 64
    settings.certification_tool_definition_bundle_sha256 = "7" * 64
    settings.certification_collector_bundle_sha256 = "8" * 64
    analysis = _completed_clear_analysis(
        report,
        analysis_id="test-analysis-id",
        org_id="test-org-id",
    )

    with (
        patch("api.services.report_access.get_settings", return_value=settings),
        patch(
            "praviar_pipeline.certification_receipt.get_pipeline_version",
            return_value="d" * 40,
        ),
        patch(
            "praviar_pipeline.certification_receipt.compute_source_tree_provenance",
            return_value=("build", "e" * 64),
        ),
    ):
        assert require_completed_report_payload(analysis) is report


def test_completed_clear_report_rejects_revoked_receipt_at_access() -> None:
    report, settings = _dsse_bound_clear_report()
    settings.certification_revoked_receipt_ids = ("test-release-receipt",)
    analysis = _completed_clear_analysis(
        report,
        analysis_id="test-analysis-id",
        org_id="test-org-id",
    )
    with (
        patch("api.services.report_access.get_settings", return_value=settings),
        patch(
            "praviar_pipeline.certification_receipt.get_pipeline_version",
            return_value="b" * 40,
        ),
        patch(
            "praviar_pipeline.certification_receipt.compute_source_tree_provenance",
            return_value=("build", "c" * 64),
        ),
        pytest.raises(APIError),
    ):
        require_completed_report_payload(analysis)


def test_contextless_clear_report_rejects_revoked_receipt() -> None:
    report, settings = _dsse_bound_clear_report()
    settings.certification_revoked_receipt_ids = ("test-release-receipt",)

    with (
        patch("api.services.report_access.get_settings", return_value=settings),
        pytest.raises(ValueError, match="certification_release_receipt_revoked"),
    ):
        validate_report_publishability(report)


@pytest.mark.parametrize(
    ("analysis_id", "org_id"),
    [("other-analysis", "test-org-id"), ("test-analysis-id", "other-org")],
)
def test_completed_clear_report_rejects_cross_owner_replay(
    analysis_id: str,
    org_id: str,
) -> None:
    report, settings = _dsse_bound_clear_report()
    analysis = _completed_clear_analysis(report, analysis_id=analysis_id, org_id=org_id)
    with (
        patch("api.services.report_access.get_settings", return_value=settings),
        patch(
            "praviar_pipeline.certification_receipt.get_pipeline_version",
            return_value="b" * 40,
        ),
        patch(
            "praviar_pipeline.certification_receipt.compute_source_tree_provenance",
            return_value=("build", "c" * 64),
        ),
        pytest.raises(APIError),
    ):
        require_completed_report_payload(analysis)


def test_completed_clear_report_rejects_hmac_without_dsse() -> None:
    report = _semantic_clear_report()
    analysis = _completed_clear_analysis(
        report,
        analysis_id="test-analysis-id",
        org_id="test-org-id",
    )

    with pytest.raises(APIError):
        require_completed_report_payload(analysis)


def test_report_publishability_rejects_post_completion_clear_report_mutation() -> None:
    report, settings = _dsse_bound_clear_report()
    report["action_items"] = ["Altered after certification binding"]

    with (
        patch("api.services.report_access.get_settings", return_value=settings),
        pytest.raises(ValueError, match="report certification binding is invalid"),
    ):
        validate_report_publishability(report)


@pytest.mark.parametrize("signal_kind", ["medium", "blocking", "unresolved"])
def test_report_publishability_rejects_clear_with_nonclear_signals(signal_kind: str):
    report, settings = _dsse_bound_clear_report()
    audit = report["clearance_decision"]["decision_audit"]
    claim_program = audit["claim_program_summary"]
    if signal_kind == "medium":
        report["claim_program_decisions"][0]["literal_risk"] = "medium"
        claim_program["medium_risk_claim_ids"] = ["US12345678A1#claim1"]
        claim_program["medium_risk_patent_ids"] = ["US12345678A1"]
    elif signal_kind == "blocking":
        report["claim_program_decisions"][0]["literal_risk"] = "high"
        claim_program["blocking_claim_ids"] = ["US12345678A1#claim1"]
        claim_program["blocking_patent_ids"] = ["US12345678A1"]
        audit["decisive_references"] = [
            {
                "category": "blocking_patent",
                "summary": "Material blocker.",
                "patent_id": "US12345678A1",
                "jurisdiction": "US",
                "source_name": "patentsview",
                "signal": "high",
            }
        ]
        report["jurisdiction_decisions"][0]["blocking_patent_ids"] = ["US12345678A1"]
        report["risk_summary"]["blocking_patents_count"] = 1
        report["risk_summary"]["executive_summary"] = (
            "Clearance decision: CLEAR. 1 blocking patent identified from 1 analyzed."
        )
    else:
        audit["insufficiency_reasons"] = ["Authoritative claim record is unresolved."]

    with (
        patch("api.services.report_access.get_settings", return_value=settings),
        pytest.raises(ValueError, match="unresolved|evidence sufficiency"),
    ):
        validate_report_publishability(report)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda report: report["verification"]["checks"][0].update({"passed": False}),
            "failed checks",
        ),
        (
            lambda report: report["verification"].update({"all_claims_grounded": False}),
            "all_claims_grounded",
        ),
        (
            lambda report: report["verification"].update({"issues": ["needs review"]}),
            "issues",
        ),
        (
            lambda report: report["verification_summary"].update({"overall_assessment": "FAIL"}),
            "overall_assessment",
        ),
        (
            lambda report: report["verification_summary"].update({"factual_accuracy_rate": 0.94}),
            "factual_accuracy_rate",
        ),
        (
            lambda report: report["verification_summary"].update(
                {
                    "claims_correct": 7,
                    "claims_incorrect": 1,
                    "factual_accuracy_rate": 0.875,
                }
            ),
            "claims_incorrect",
        ),
        (
            lambda report: report["verification_summary"].update(
                {
                    "claims_correct": 7,
                    "claims_unverifiable": 1,
                    "factual_accuracy_rate": 0.875,
                }
            ),
            "claims_unverifiable",
        ),
        (
            lambda report: report["verification_summary"].update(
                {"corrections_needed": [{"section_id": "risk_summary"}]}
            ),
            "corrections_needed",
        ),
        (
            lambda report: report["verification_summary"].update(
                {
                    "total_claims_checked": 0,
                    "claims_correct": 0,
                    "factual_accuracy_rate": 0.0,
                }
            ),
            "total_claims_checked",
        ),
        (
            lambda report: report["verification_summary"].update({"total_claims_checked": 9}),
            "categorized claim counts",
        ),
        (
            lambda report: report["verification_summary"].update({"factual_accuracy_rate": 0.99}),
            "does not match claim counts",
        ),
        (
            lambda report: report["verification_summary"].pop("factual_accuracy_rate"),
            "factual_accuracy_rate must be numeric",
        ),
    ],
)
def test_validate_report_publishability_rejects_failed_verification_metadata(
    mutation,
    message,
):
    report = deepcopy(valid_report_data())
    mutation(report)

    with pytest.raises(ValueError, match=message):
        validate_report_publishability(report)

    analysis = MagicMock(
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    with pytest.raises(APIError) as exc_info:
        require_completed_report_payload(analysis)

    assert exc_info.value.status == 404


def _strip_material_assertion_support(report: dict) -> None:
    support_map = report["claim_source_span_map"]
    for entry in support_map["entries"]:
        entry["patent_id"] = ""
    for span in support_map["spans"].values():
        span["patent_id"] = ""

    report["patent_analyses"] = []
    decision_audit = report["clearance_decision"]["decision_audit"]
    decision_audit["decisive_references"] = []
    decision_audit["insufficiency_reasons"] = []
    decision_audit["claim_program_summary"]["blocking_patent_ids"] = []
    decision_audit["claim_program_summary"]["medium_risk_patent_ids"] = []
    decision_audit["coverage_summary"]["reviewed_patent_ids"] = []
    report["jurisdiction_decisions"] = []
    report["evidence_artifacts"] = []
    report["prosecution_dossiers"] = []
    evidence_index = report.get("matter_evidence_index") or {}
    evidence_index["patent_records"] = []
    evidence_index["family_records"] = []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            _strip_material_assertion_support,
            "verified claim source span",
        ),
        (
            lambda report: (
                report["clearance_decision"].update({"decision": "clear"}),
                report["clearance_decision"]["decision_audit"].update({"decisive_references": []}),
            ),
            "clearance_decision clear",
        ),
        (
            lambda report: (
                report["clearance_decision"].update({"decision": "blocked"}),
                report["clearance_decision"]["decision_audit"].update({"decisive_references": []}),
                report["clearance_decision"]["decision_audit"]["claim_program_summary"].update(
                    {"blocking_patent_ids": []}
                ),
            ),
            "clearance_decision blocked",
        ),
        (
            lambda report: report.update(
                {
                    "jurisdiction_decisions": [
                        {
                            "jurisdiction": "US",
                            "decision": "unclear",
                            "gate_failures": [],
                            "reviewed_patent_ids": [],
                            "blocking_patent_ids": [],
                            "reasoning": [],
                        }
                    ]
                }
            ),
            "jurisdiction_decisions",
        ),
    ],
)
def test_validate_report_publishability_rejects_unsupported_material_assertions(
    mutation,
    message,
):
    report = deepcopy(valid_report_data())
    mutation(report)

    with pytest.raises(ValueError, match=message):
        validate_report_publishability(report)


def test_validate_report_publishability_rejects_mismatched_material_source_span_support():
    report = deepcopy(valid_report_data())
    support_map = report["claim_source_span_map"]
    for entry in support_map["entries"]:
        entry["patent_id"] = "US99999999A1"
    for span in support_map["spans"].values():
        span["patent_id"] = "US99999999A1"

    with pytest.raises(ValueError, match="verified claim source span"):
        validate_report_publishability(report)


def test_validate_report_publishability_rejects_unsupported_patent_analysis_rows():
    report = deepcopy(
        valid_report_data(
            patent_analyses=[
                {
                    "patent_id": "US91000013A1",
                    "title": "Unsupported patent row",
                    "assignee": "Example Pharma",
                    "risk_level": "medium",
                    "expiry_date": "2035-01-01",
                }
            ]
        )
    )

    with pytest.raises(ValueError, match="patent_analyses"):
        validate_report_publishability(report)


def test_validate_report_publishability_rejects_unsupported_evidence_inventory_patents():
    report = deepcopy(valid_report_data())
    report["matter_evidence_index"]["patent_records"] = [
        {
            "patent_id": "US99999999A1",
            "title": "Unsupported orphan patent evidence record",
            "legal_status": "active",
            "risk_level": "high",
            "authoritative_source_names": ["patentsview"],
        }
    ]

    with pytest.raises(ValueError, match="material report patents"):
        validate_report_publishability(report)


def test_build_governed_report_summary_rejects_semantically_invalid_report_fields():
    report = valid_report_data(
        risk_summary={
            "overall_risk": "not-a-risk-level",
            "blocking_patents_count": "not-a-count",
            "total_patents_analyzed": None,
            "executive_summary": "",
        }
    )
    analysis = MagicMock(
        status=AnalysisStatus.COMPLETED,
        report_data=report,
        overall_risk="high",
        blocking_patents_count=2,
        total_patents_found=8,
        executive_summary="Fallback summary from analysis columns.",
    )

    with pytest.raises(APIError) as exc_info:
        build_governed_report_summary(analysis)

    assert exc_info.value.status == 404
    assert "not yet available" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_load_report_for_org_authorizes_before_returning_cached_report(mock_db):
    report = valid_report_data()
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        org_id=org_id,
        report_data=report,
    )

    async def _cached_after_authorization(
        _org_id: str,
        _analysis_id: str,
        *,
        version: str,
    ) -> dict:
        assert mock_db.execute.await_count == 2
        assert version == report_payload_fingerprint(report)
        return report

    with patch(
        "api.services.report_content.get_cached_report",
        new=AsyncMock(side_effect=_cached_after_authorization),
    ) as get_cache:
        loaded = await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    assert loaded["report_id"] == report["report_id"]
    get_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        version=report_payload_fingerprint(report),
    )
    assert mock_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_report_for_org_rejects_cached_report_when_analysis_not_in_org(mock_db):
    report = valid_report_data(report_id="cross-org-cached-report")
    mock_db.execute.side_effect = [_scalar_result(None)]

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=report),
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    assert "Analysis not found" in str(exc_info.value)
    get_cache.assert_not_awaited()
    assert mock_db.execute.await_count == 1


@pytest.mark.asyncio
async def test_load_report_for_org_rejects_cached_report_when_report_not_available(mock_db):
    analysis_id = uuid.uuid4()
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        has_report_data=False,
    )

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=valid_report_data(report_id="stale-cached-report")),
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    assert "Report not yet available" in str(exc_info.value)
    get_cache.assert_not_awaited()
    assert mock_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_report_for_org_rejects_cached_report_when_report_payload_empty(mock_db):
    analysis_id = uuid.uuid4()
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        has_report_data=False,
    )

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=valid_report_data(report_id="stale-cache-empty-db-payload")),
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    assert "Report not yet available" in str(exc_info.value)
    get_cache.assert_not_awaited()
    assert mock_db.execute.await_count == 2
    status_query = str(mock_db.execute.await_args_list[0].args[0])
    payload_query = str(mock_db.execute.await_args_list[1].args[0])
    assert "analyses.org_id" in status_query
    assert "analyses.org_id" in payload_query
    assert "analyses.status" in payload_query
    assert "analyses.report_data IS NOT NULL" in payload_query
    assert "jsonb_typeof(analyses.report_data)" in payload_query
    assert "analyses.report_data !=" in payload_query
    assert "analyses.report_data" in payload_query


@pytest.mark.asyncio
async def test_load_report_for_org_rejects_cached_report_when_db_lacks_source_span_map(mock_db):
    analysis_id = uuid.uuid4()
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        has_report_data=False,
    )

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=valid_report_data(report_id="stale-cache-with-provenance")),
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    get_cache.assert_not_awaited()
    assert mock_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_report_for_org_rejects_cache_when_db_source_span_map_empty(mock_db):
    analysis_id = uuid.uuid4()
    empty_provenance_report = valid_report_data(
        claim_source_span_map={
            "generated_from": "empty_db_map",
            "entries": [],
            "spans": {},
            "unsupported_customer_visible_claim_count": 0,
            "needs_review_count": 0,
        }
    )
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        report_data=empty_provenance_report,
    )

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=valid_report_data(report_id="stale-cache-valid-map")),
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    assert "Report not yet available" in str(exc_info.value)
    get_cache.assert_not_awaited()
    assert mock_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_report_for_org_reloads_db_when_cached_report_lacks_source_span_map(mock_db):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = valid_report_data(report_id="db-report-with-provenance")
    cached_report = dict(report)
    cached_report.pop("claim_source_span_map")
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    mock_db.execute.side_effect = [
        *_authorized_report_query_results(
            analysis_id,
            org_id=org_id,
            report_data=report,
        ),
        _scalar_result(analysis),
    ]

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=cached_report),
        ) as get_cache,
        patch("api.services.report_content.set_cached_report", new=AsyncMock()) as set_cache,
    ):
        loaded = await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    assert loaded["report_id"] == "db-report-with-provenance"
    report_version = report_payload_fingerprint(report)
    get_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        version=report_version,
    )
    set_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        report,
        version=report_version,
    )


@pytest.mark.asyncio
async def test_load_report_for_org_reloads_db_when_cached_report_fails_publishability(mock_db):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = valid_report_data(report_id="db-report-publishable")
    cached_report = deepcopy(report)
    cached_report["verification_summary"]["claims_incorrect"] = 1
    cached_report["verification_summary"]["factual_accuracy_rate"] = 0.8
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    mock_db.execute.side_effect = [
        *_authorized_report_query_results(
            analysis_id,
            org_id=org_id,
            report_data=report,
        ),
        _scalar_result(analysis),
    ]

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=cached_report),
        ) as get_cache,
        patch("api.services.report_content.set_cached_report", new=AsyncMock()) as set_cache,
    ):
        loaded = await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    assert loaded["report_id"] == "db-report-publishable"
    report_version = report_payload_fingerprint(report)
    get_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        version=report_version,
    )
    set_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        report,
        version=report_version,
    )


@pytest.mark.asyncio
async def test_load_report_for_org_rejects_cached_report_when_db_report_fails_publishability(
    mock_db,
):
    analysis_id = uuid.uuid4()
    db_report = valid_report_data(report_id="db-report-no-longer-publishable")
    db_report["verification_summary"]["claims_incorrect"] = 1
    db_report["verification_summary"]["factual_accuracy_rate"] = 0.8
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        report_data=db_report,
    )

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=valid_report_data(report_id="stale-valid-cache")),
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    assert "Report not yet available" in str(exc_info.value)
    get_cache.assert_not_awaited()
    assert mock_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_report_for_org_reloads_db_when_cached_report_lacks_material_assertion_support(
    mock_db,
):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = valid_report_data(report_id="db-report-materially-supported")
    cached_report = deepcopy(report)
    _strip_material_assertion_support(cached_report)
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    mock_db.execute.side_effect = [
        *_authorized_report_query_results(
            analysis_id,
            org_id=org_id,
            report_data=report,
        ),
        _scalar_result(analysis),
    ]

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=cached_report),
        ) as get_cache,
        patch("api.services.report_content.set_cached_report", new=AsyncMock()) as set_cache,
    ):
        loaded = await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    assert loaded["report_id"] == "db-report-materially-supported"
    report_version = report_payload_fingerprint(report)
    get_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        version=report_version,
    )
    set_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        report,
        version=report_version,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [AnalysisStatus.RUNNING, AnalysisStatus.DELETED])
async def test_load_report_for_org_rejects_cached_report_when_analysis_not_completed(
    mock_db,
    status: AnalysisStatus,
):
    analysis_id = uuid.uuid4()
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        status=status,
    )

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=valid_report_data(report_id="stale-cached-report")),
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    assert "Report not yet available" in str(exc_info.value)
    get_cache.assert_not_awaited()
    assert mock_db.execute.await_count == 1


@pytest.mark.asyncio
async def test_load_report_for_org_loads_db_and_populates_cache(mock_db):
    report = valid_report_data()
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = analysis
    mock_db.execute.side_effect = [
        *_authorized_report_query_results(
            analysis_id,
            org_id=org_id,
            report_data=report,
        ),
        _scalar_result(analysis),
    ]

    with (
        patch("api.services.report_content.get_cached_report", new=AsyncMock(return_value=None)),
        patch("api.services.report_content.set_cached_report", new=AsyncMock()) as set_cache,
    ):
        loaded = await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    assert loaded["report_id"] == report["report_id"]
    set_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        report,
        version=report_payload_fingerprint(report),
    )


@pytest.mark.asyncio
async def test_load_report_for_org_rejects_stale_cached_report_after_rerun(mock_db):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    current_report = valid_report_data(report_id="rerun-current-report")
    stale_report = valid_report_data(report_id="rerun-stale-report")
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=current_report,
    )
    mock_db.execute.side_effect = [
        *_authorized_report_query_results(
            analysis_id,
            org_id=org_id,
            report_data=current_report,
        ),
        _scalar_result(analysis),
    ]

    with (
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(return_value=stale_report),
        ) as get_cache,
        patch("api.services.report_content.set_cached_report", new=AsyncMock()) as set_cache,
    ):
        loaded = await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    current_version = report_payload_fingerprint(current_report)
    assert loaded["report_id"] == "rerun-current-report"
    get_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        version=current_version,
    )
    set_cache.assert_awaited_once_with(
        str(org_id),
        str(analysis_id),
        current_report,
        version=current_version,
    )


@pytest.mark.asyncio
async def test_load_report_for_org_fails_closed_in_prod_on_cache_read_failure(mock_db):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        org_id=org_id,
    )

    with (
        patch(
            "api.services.report_content.get_settings",
            return_value=SimpleNamespace(app_env="prod"),
        ),
        patch(
            "api.services.report_content.get_cached_report",
            new=AsyncMock(side_effect=RuntimeError("redis unavailable")),
        ),
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    assert exc_info.value.status == 503
    assert mock_db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_report_for_org_fails_closed_in_prod_on_cache_write_failure(mock_db):
    report = valid_report_data()
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
    )
    mock_db.execute.side_effect = [
        *_authorized_report_query_results(
            analysis_id,
            org_id=org_id,
            report_data=report,
        ),
        _scalar_result(analysis),
    ]

    with (
        patch(
            "api.services.report_content.get_settings",
            return_value=SimpleNamespace(app_env="prod"),
        ),
        patch("api.services.report_content.get_cached_report", new=AsyncMock(return_value=None)),
        patch(
            "api.services.report_content.set_cached_report",
            new=AsyncMock(side_effect=RuntimeError("redis unavailable")),
        ),
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=org_id,
        )

    assert exc_info.value.status == 503


@pytest.mark.asyncio
async def test_load_report_for_org_raises_when_report_missing(mock_db):
    analysis_id = uuid.uuid4()
    mock_db.execute.side_effect = _authorized_report_query_results(
        analysis_id,
        has_report_data=False,
    )

    with (
        patch(
            "api.services.report_content.get_cached_report", new=AsyncMock(return_value=None)
        ) as get_cache,
        pytest.raises(APIError) as exc_info,
    ):
        await load_report_for_org(
            mock_db,
            analysis_id=analysis_id,
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404
    get_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_report_summary_for_org_uses_governed_report_payload_summary(mock_db):
    analysis_id = uuid.uuid4()
    org_id = uuid.uuid4()
    report = valid_report_data(
        total_patents_found=4,
        risk_summary={
            "overall_risk": "medium",
            "blocking_patents_count": 0,
            "total_patents_analyzed": 1,
            "key_risks": [],
            "executive_summary": (
                "Clearance decision: UNCLEAR. 0 blocking patents identified from 1 analyzed."
            ),
        },
    )
    report["audit_trail"].update(
        {
            "total_patents_discovered": 4,
            "patents_after_hard_filter": 4,
            "patents_after_ranking": 2,
        }
    )
    report["report_certification_binding"] = sign_report_certification_binding(
        report,
        signer=ReportCertificationSigner.from_secret(
            TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET
        ),
        analysis_id=str(analysis_id),
        org_id=str(org_id),
    )
    analysis = MagicMock(
        id=analysis_id,
        org_id=org_id,
        status=AnalysisStatus.COMPLETED,
        report_data=report,
        overall_risk="high",
        blocking_patents_count=99,
        total_patents_found=500,
        executive_summary="Stale unsupported column summary",
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = analysis

    summary = await get_report_summary_for_org(
        mock_db,
        analysis_id=analysis_id,
        org_id=org_id,
    )

    assert summary == {
        "overall_risk": "medium",
        "blocking_patents_count": 0,
        "total_patents_found": 4,
        "executive_summary": "Clearance decision: UNCLEAR. 0 blocking patents identified from 1 analyzed.",
        "risk_ratings_restricted": False,
    }


@pytest.mark.asyncio
async def test_get_report_summary_for_org_rejects_non_completed_report_payload(mock_db):
    analysis = MagicMock(
        status=AnalysisStatus.RUNNING,
        report_data=valid_report_data(),
        overall_risk="high",
        blocking_patents_count=7,
        total_patents_found=42,
        executive_summary="stale running report summary",
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = analysis

    with pytest.raises(APIError) as exc_info:
        await get_report_summary_for_org(
            mock_db,
            analysis_id=uuid.uuid4(),
            org_id=uuid.uuid4(),
        )

    assert exc_info.value.status == 404


def test_search_report_content_matches_multiple_sections():
    results = search_report_content(_searchable_report(), "aspirin")

    assert results["total"] >= 2
    assert {item["section"] for item in results["results"]} >= {
        "patent_analysis",
        "executive_summary",
    }

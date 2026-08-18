from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.services.public_reports import (
    _https_url,
    _public_limitation_category,
    _public_patent_reference,
    _shared_evidence_limitation_candidates,
    _shared_integrity_summary,
    build_shared_report_payload,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://PATENTS.GOOGLE.COM./patent/US123?oq=aspirin#claims",
            "https://patents.google.com/patent/US123?oq=aspirin",
        ),
        ("http://patents.google.com/patent/US123", ""),
        ("https://user@patents.google.com/patent/US123", ""),
        ("https://patents.google.com:444/patent/US123", ""),
        ("https://example.com/patent/US123", ""),
        ("https://127.0.0.1/patent/US123", ""),
        ("https://patents.google.com:bad/patent/US123", ""),
        ("", ""),
    ],
)
def test_https_url_only_allows_normalised_public_evidence_hosts(url: str, expected: str) -> None:
    assert _https_url(url) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("US-123-A1", "US-123-A1"),
        ("../../etc/passwd", ""),
        ("https://example.com", ""),
        ("", ""),
    ],
)
def test_public_patent_reference_rejects_non_patent_identifiers(value: str, expected: str) -> None:
    assert _public_patent_reference(value) == expected


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        ("Missing independent claim text", "Claim text or claim-level evidence requires review"),
        ("File wrapper incomplete", "Prosecution history context requires review"),
        ("Register status stale", "Patent register/status context requires review"),
        ("Family coverage incomplete", "Patent family context requires review"),
        ("Provider timeout", "Source coverage requires review"),
        ("postgresql://secret@db/prod", "Evidence caveat requires counsel review"),
    ],
)
def test_public_limitation_category_coarsens_internal_diagnostics(raw: str, category: str) -> None:
    assert _public_limitation_category(raw) == category


def _report_data() -> dict:
    return {
        "report_id": "report-123",
        "source_snapshot_at": "2026-08-03T12:00:00Z",
        "praviar_pipeline_version": "3.0.0",
        "llm_models_used": {"writer": "model-b", "reviewer": "model-a", "empty": ""},
        "risk_summary": {
            "key_risks": ["Risk one", "Risk two", "Risk three", "Risk four", "Risk five"],
            "total_patents_analyzed": 7,
        },
        "patent_analyses": [
            {
                "patent_id": "US-LOW-A1",
                "risk_level": "low",
                "assignee": "Low Corp",
                "source_name": "patentsview",
            },
            {
                "publication_number": "US-BLOCK-A1",
                "risk_level": "low",
                "owner": "Block Corp",
                "blocking": True,
            },
            {
                "patent_number": "US-MED-A1",
                "risk_level": "clear",
                "source": "unknown internal adapter",
            },
            {"patent_id": "US-LOW-A1", "risk_level": "high"},
            {
                "patent_id": "not a patent",
                "risk_level": "medium",
                "source_url": "https://register.epo.org/espacenet/application?number=EP1#top",
            },
        ],
        "target_jurisdictions": ["US", "EP", "GB", "CA", "AU", "JP", "KR"],
        "analysis_failures": [
            {"patent_id": "US-1", "recoverable": True},
            {"patent_id": "US-2", "recoverable": False},
        ],
        "data_limitations": [{"kind": "claims"}],
        "clearance_decision": {
            "decision_audit": {
                "analysis_failures_count": 3,
                "material_patents_reviewed": 6,
                "evidence_sufficient_for_clearance": False,
                "insufficiency_reasons": ["File wrapper incomplete"],
                "claim_program_summary": {
                    "blocking_patent_ids": ["US-BLOCK-A1"],
                    "medium_risk_patent_ids": ["US-MED-A1"],
                },
                "coverage_summary": {
                    "successful_source_names": [
                        "patentsview",
                        "pubchem_sdq",
                        "bigquery",
                        "epo_ops",
                        "uspto",
                        "extra",
                    ],
                    "failed_source_names": ["google_patents", "praviar-prod database"],
                    "failed_analysis_patent_ids": ["US-1"],
                    "reviewed_patent_ids": ["US-BLOCK-A1", "US-MED-A1"],
                    "patents_missing_claims": ["US-MISSING-A1", "/tmp/private.txt"],
                    "verification_gaps": [
                        "Family coverage incomplete",
                        "postgresql://secret@db/prod",
                    ],
                },
            }
        },
    }


def _analysis(report_data: dict) -> SimpleNamespace:
    analysis = SimpleNamespace(
        id=uuid.uuid4(),
        compound_name="Aspirin",
        updated_at=NOW,
        report_data=report_data,
    )
    analysis.__dict__.update(
        {
            "_share_expires_at": NOW + timedelta(days=7),
            "_share_recipient_email": "counsel@example.com",
            "_share_view_number": 3,
            "_share_access_expires_at": NOW + timedelta(minutes=20),
            "_share_id": uuid.uuid4(),
            "_share_report_fingerprint": "f" * 64,
            "_share_review_status": SimpleNamespace(status=SimpleNamespace(value="approved")),
        }
    )
    return analysis


def test_build_shared_report_payload_prioritises_risk_and_sanitises_public_metadata() -> None:
    report_data = _report_data()
    analysis = _analysis(report_data)

    with (
        patch(
            "api.services.public_reports.require_completed_report_payload",
            return_value=report_data,
        ),
        patch(
            "api.services.public_reports.build_governed_report_summary",
            return_value={
                "overall_risk": "medium",
                "blocking_patents_count": 1,
                "total_patents_found": 7,
                "executive_summary": "Counsel review required.",
            },
        ),
    ):
        payload = build_shared_report_payload(analysis)

    assert payload["key_findings"] == ["Risk one", "Risk two", "Risk three", "Risk four"]
    assert [patent["patent_number"] for patent in payload["key_patents"]] == [
        "US-BLOCK-A1",
        "US-MED-A1",
        "not a patent",
    ]
    assert [patent["risk_level"] for patent in payload["key_patents"]] == [
        "high",
        "medium",
        "medium",
    ]
    assert payload["key_patents"][0]["patent_url"].startswith("https://patents.google.com/patent/")
    assert payload["key_patents"][2]["patent_url"].startswith("https://register.epo.org/")
    assert payload["source_coverage"] == [
        "PatentsView",
        "PubChem SDQ",
        "Google patent datasets",
        "EPO OPS",
        "USPTO",
    ]
    assert payload["jurisdiction_scope"] == ["US", "EP", "GB", "CA", "AU", "JP"]
    assert payload["integrity_summary"] == {
        "affected_patents_count": 3,
        "recoverable_failures_count": 1,
        "needs_review_count": 2,
        "data_limitations_count": 1,
        "source_caveats_count": 8,
        "evidence_sufficient_for_clearance": False,
        "metadata_inconsistent": True,
    }
    assert payload["total_material_patents"] == 7
    assert payload["omitted_key_patents_count"] == 4
    assert payload["model_version"] == "model-a, model-b"
    assert payload["review_status"] == "approved"
    serialised = repr(payload)
    assert "postgresql://" not in serialised
    assert "/tmp/private.txt" not in serialised
    assert "praviar-prod" not in serialised


def test_evidence_limitations_report_inconsistency_and_deduplicate_categories() -> None:
    report_data = _report_data()

    limitations = _shared_evidence_limitation_candidates(report_data)
    integrity = _shared_integrity_summary(report_data)

    assert limitations[0] == "Report metadata counts require verification"
    assert "Evidence coverage is screening-only until listed gaps are reviewed" in limitations
    assert "3 patent analyses require review" in limitations
    assert "1 recoverable processing issue" in limitations
    assert "1 data coverage limitation detected" in limitations
    assert limitations.count("Evidence caveat requires counsel review") == 1
    assert integrity["metadata_inconsistent"] is True


def test_build_shared_report_payload_falls_back_to_analysis_timestamps_and_reasoning() -> None:
    report_data = {
        "clearance_decision": {
            "decision_reasoning": ["Reason one", "Reason two"],
            "decision_audit": {
                "coverage_summary": {},
                "claim_program_summary": {},
            },
        },
        "certification_scope": {"certified_jurisdictions": ["US"]},
    }
    analysis = _analysis(report_data)

    with (
        patch(
            "api.services.public_reports.require_completed_report_payload",
            return_value=report_data,
        ),
        patch(
            "api.services.public_reports.build_governed_report_summary",
            return_value={
                "overall_risk": "low",
                "blocking_patents_count": 0,
                "total_patents_found": 0,
                "executive_summary": "No material evidence found.",
            },
        ),
    ):
        payload = build_shared_report_payload(analysis)

    assert payload["report_id"] == str(analysis.id)
    assert payload["generated_at"] == NOW.isoformat()
    assert payload["key_findings"] == ["Reason one", "Reason two"]
    assert payload["jurisdiction_scope"] == ["US"]
    assert payload["key_patents"] == []

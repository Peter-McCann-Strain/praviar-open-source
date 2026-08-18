"""Tests for structured prosecution-context parsing."""

from __future__ import annotations

from praviar_pipeline.pipeline.analysis import prosecution_parsing as module
from praviar_pipeline.pipeline.analysis.prosecution_parsing import (
    build_prosecution_context_payload,
)


def test_build_prosecution_context_payload_derives_doctrine_flags() -> None:
    payload = build_prosecution_context_payload(
        office_actions=[
            {
                "documentCode": "CTFR",
                "documentDescription": "Final Office Action under 35 U.S.C. 103",
                "mailDate": "2025-01-02",
                "claimsRejected": [1, 2],
                "rejectionBasis": "103 obviousness over Smith",
            }
        ],
        continuity=[
            {
                "parentApplicationNumberText": "12/111111",
                "claimTypeCd": "CON",
                "filingDate": "2023-01-10",
            },
            {
                "childApplicationNumberText": "17/222222",
                "claimTypeCd": "DIV",
                "filingDate": "2025-02-11",
            },
        ],
        transactions=[
            {
                "transactionCode": "AMND",
                "transactionDescription": "Amendment after final to claims 1-2",
                "transactionDate": "2025-02-03",
            },
            {
                "transactionCode": "RCE",
                "transactionDescription": "Request for Continued Examination",
                "transactionDate": "2025-03-04",
            },
            {
                "transactionCode": "EXIN",
                "transactionDescription": "Examiner interview summary",
                "transactionDate": "2025-03-08",
            },
        ],
        file_wrapper_documents=[{"documentIdentifier": "FW1"}],
    )

    assert payload["office_action_types"] == ["final_office_action"]
    assert payload["continuity_types"] == ["continuation", "divisional"]
    assert payload["amendment_types"] == ["after_final_response", "rce", "interview"]
    assert payload["rejection_bases"] == ["103", "prior_art"]
    assert payload["continuation_parent_count"] == 1
    assert payload["divisional_child_count"] == 1
    assert payload["response_after_final_count"] == 1
    assert payload["rce_count"] == 1
    assert payload["interview_event_count"] == 1
    assert payload["estoppel_risk_flags"] == [
        "after_final_response_history",
        "rce_history",
        "interview_history",
        "continuation_lineage",
        "divisional_lineage",
        "prior_art_rejection_history",
        "amendment_after_office_action_history",
    ]
    assert payload["office_action_events"][0]["rejection_bases"] == ["103", "prior_art"]
    assert payload["office_action_events"][0]["claims_rejected"] == [1, 2]
    assert payload["continuity_entries"][1]["relationship"] == "child"
    assert payload["amendment_events"][0]["event_type"] == "after_final_response"
    assert payload["amendment_events"][0]["claim_numbers"] == [1, 2]
    assert payload["rejected_claim_numbers"] == [1, 2]
    assert payload["narrowing_claim_numbers"] == [1, 2]
    assert payload["file_wrapper_document_count"] == 1
    assert "us_file_wrapper_dossier" in payload["sections_available"]


def test_build_prosecution_context_payload_uses_module_patch_points(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "normalize_office_action_events",
        lambda office_actions: [{"office_action_type": "patched"}],
    )
    monkeypatch.setattr(
        module,
        "normalize_continuity_entries",
        lambda continuity: [{"continuity_type": "patched", "relationship": "parent"}],
    )
    monkeypatch.setattr(
        module,
        "normalize_amendment_events",
        lambda transactions: [{"event_type": "patched"}],
    )
    monkeypatch.setattr(
        module,
        "derive_prosecution_profile",
        lambda **kwargs: {"patched_profile": True},
    )

    payload = build_prosecution_context_payload(
        office_actions=[{"documentCode": "CTFR"}],
        continuity=[{"parentApplicationNumberText": "12/111111"}],
        transactions=[{"transactionCode": "AMND"}],
    )

    assert payload["office_action_events"] == [{"office_action_type": "patched"}]
    assert payload["continuity_entries"] == [
        {"continuity_type": "patched", "relationship": "parent"}
    ]
    assert payload["amendment_events"] == [{"event_type": "patched"}]
    assert payload["patched_profile"] is True

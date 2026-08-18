"""Tests for prosecution parsing helper functions."""

from __future__ import annotations

from praviar_pipeline.pipeline.analysis.prosecution_parsing_helpers import (
    classify_office_action_type,
    classify_transaction_type,
    derive_prosecution_profile,
    extract_rejection_bases,
    normalize_amendment_events,
    normalize_continuity_entries,
    normalize_continuity_type,
    normalize_office_action_events,
)


def test_normalize_office_action_events_derives_types_and_bases() -> None:
    events = normalize_office_action_events(
        [
            {
                "documentCode": "CTFR",
                "documentDescription": "Final Office Action under 35 U.S.C. 103",
                "mailDate": "2025-01-02",
                "claimsRejected": [1, "2", "x"],
                "rejectionBasis": "103 obviousness over Smith",
            }
        ]
    )

    assert events == [
        {
            "document_code": "CTFR",
            "description": "Final Office Action under 35 U.S.C. 103",
            "event_date": "2025-01-02",
            "office_action_type": "final_office_action",
            "claims_rejected": [1, 2],
            "rejection_bases": ["103", "prior_art"],
        }
    ]


def test_normalize_continuity_entries_and_amendments() -> None:
    continuity_entries = normalize_continuity_entries(
        [
            {
                "parentApplicationNumberText": "12/111111",
                "claimTypeCd": "CON",
                "filingDate": "2023-01-10",
            },
            {
                "childApplicationNumberText": "17/222222",
                "continuityType": "divisional",
                "filingDate": "2025-02-11",
            },
        ]
    )
    amendment_events = normalize_amendment_events(
        [
            {
                "transactionCode": "AMND",
                "transactionDescription": "Amendment after final to claims 1-2 and 4",
                "transactionDate": "2025-02-03",
            },
            {
                "transactionCode": "RCE",
                "transactionDescription": "Request for Continued Examination",
                "transactionDate": "2025-03-04",
            },
        ]
    )

    assert continuity_entries == [
        {
            "relationship": "parent",
            "application_number": "12/111111",
            "related_application_number": "",
            "continuity_type": "continuation",
            "filing_date": "2023-01-10",
        },
        {
            "relationship": "child",
            "application_number": "17/222222",
            "related_application_number": "",
            "continuity_type": "divisional",
            "filing_date": "2025-02-11",
        },
    ]
    assert amendment_events == [
        {
            "transaction_code": "AMND",
            "description": "Amendment after final to claims 1-2 and 4",
            "event_date": "2025-02-03",
            "event_type": "after_final_response",
            "claim_numbers": [1, 2, 4],
        },
        {
            "transaction_code": "RCE",
            "description": "Request for Continued Examination",
            "event_date": "2025-03-04",
            "event_type": "rce",
            "claim_numbers": [],
        },
    ]


def test_derive_prosecution_profile_collects_risk_flags() -> None:
    profile = derive_prosecution_profile(
        office_action_events=[
            {
                "office_action_type": "final_office_action",
                "rejection_bases": ["103", "prior_art"],
            }
        ],
        continuity_entries=[
            {
                "continuity_type": "continuation",
                "relationship": "parent",
            }
        ],
        amendment_events=[
            {
                "event_type": "after_final_response",
            }
        ],
    )

    assert profile["office_action_types"] == ["final_office_action"]
    assert profile["rejection_bases"] == ["103", "prior_art"]
    assert profile["estoppel_risk_flags"] == [
        "after_final_response_history",
        "continuation_lineage",
        "prior_art_rejection_history",
        "amendment_after_office_action_history",
    ]


def test_low_level_classifiers_cover_edge_cases() -> None:
    assert (
        classify_office_action_type(
            {"documentCode": "NFOA", "documentDescription": "Non final office action"}
        )
        == "non_final_office_action"
    )
    assert normalize_continuity_type({"claimTypeCd": "continuation-in-part"}) == "cip"
    assert (
        classify_transaction_type(
            {"transactionCode": "EXIN", "transactionDescription": "Examiner interview summary"}
        )
        == "interview"
    )
    assert extract_rejection_bases(
        "Written description rejection under 35 U.S.C. 112 and obviousness-type double patenting"
    ) == ["112_a", "double_patenting"]

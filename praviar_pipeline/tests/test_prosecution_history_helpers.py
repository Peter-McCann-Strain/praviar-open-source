"""Tests for deterministic prosecution-history helper functions."""

from __future__ import annotations

from praviar_pipeline.utils.prosecution_history_helpers import (
    build_rejections_from_documents,
    build_rejections_from_office_actions,
    count_documents_of_type,
    extract_applicant_arguments,
    extract_application_number,
    extract_attorney_name,
    extract_current_assignee,
    extract_filing_date,
    extract_grant_date,
    extract_inventor_names,
    identify_narrowing_amendments,
    parse_optional_date,
)


def test_extract_application_number_prefers_text_over_metadata() -> None:
    app_data = {"applicationNumberText": "16/000001", "applicationNumber": "fallback"}
    meta = {"applicationNumber": "meta"}

    assert extract_application_number(app_data, meta) == "16/000001"


def test_extract_metadata_helpers_normalize_values() -> None:
    app_data = {
        "grantDocumentMetaData": {"grantDate": "2020-05-02"},
        "recordAttorney": {"registrationNumber": "12345"},
        "assignmentBag": [{"conveyanceText": "Acme Corp"}],
    }
    meta = {
        "filingDate": "2018-03-10",
        "inventorBag": [
            {"inventorNameText": "Jane Inventor"},
            {"inventorNameText": "US8000000B2"},
        ],
    }

    assert extract_filing_date(meta).isoformat() == "2018-03-10"
    assert extract_grant_date(meta, app_data).isoformat() == "2020-05-02"
    assert extract_inventor_names(meta, "US8000000B2") == ["Jane Inventor"]
    assert extract_attorney_name(app_data) == "12345"
    assert extract_current_assignee(app_data) == "Acme Corp"


def test_build_rejections_and_counts_from_documents() -> None:
    documents = [
        {"documentCode": "CTNF", "documentDescription": "Non-Final Rejection under 35 USC 103"},
        {"documentCode": "RES", "documentDescription": "Applicant Response/Amendment"},
        {"documentCode": "NOA", "documentDescription": "Notice of Allowance"},
    ]

    rejections = build_rejections_from_documents(documents)

    assert len(rejections) == 1
    assert rejections[0].rejection_type == "103"
    assert count_documents_of_type(documents, "rejection") == 1
    assert count_documents_of_type(documents, "response") == 1
    assert count_documents_of_type(documents, "notice_of_allowance") == 1
    assert extract_applicant_arguments(documents) == ["Applicant Response/Amendment"]


def test_build_rejections_from_office_actions_normalizes_claims() -> None:
    oa_data = [
        {
            "rejectionBasis": "35 U.S.C. 112, first paragraph",
            "claimsRejected": [1, "2", "x"],
            "citedReferences": ["US5000000", 6000000],
        }
    ]

    rejections = build_rejections_from_office_actions(oa_data)

    assert len(rejections) == 1
    assert rejections[0].rejection_type == "112_a"
    assert rejections[0].claims_rejected == [1, 2]
    assert rejections[0].prior_art_cited == ["US5000000", "6000000"]


def test_identify_narrowing_amendments_uses_timing() -> None:
    documents = [
        {
            "documentCode": "CTNF",
            "documentDescription": "Office Action",
            "documentDate": "2018-03-10",
        },
        {
            "documentCode": "A..",
            "documentDescription": "Amendment After Final",
            "documentDate": "2018-06-10",
        },
    ]

    amendments = identify_narrowing_amendments(documents)

    assert len(amendments) == 1
    assert amendments[0].narrowing is True
    assert amendments[0].response_to_rejection is True
    assert parse_optional_date("2018-06-10T12:00:00Z").isoformat() == "2018-06-10"

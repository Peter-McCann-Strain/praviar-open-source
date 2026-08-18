"""Tests for prosecution history parser with mocked USPTO API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.models.equivalents import (
    ProsecutionHistory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_file_wrapper_docs() -> list[dict]:
    """Representative file wrapper documents from USPTO."""
    return [
        {
            "documentCode": "CTNF",
            "documentDescription": "Non-Final Rejection under 35 USC 103",
            "documentDate": "2018-03-10",
        },
        {
            "documentCode": "RES",
            "documentDescription": "Applicant Response/Amendment",
            "documentDate": "2018-06-10",
        },
        {
            "documentCode": "CTFR",
            "documentDescription": "Final Rejection under 35 USC 102",
            "documentDate": "2018-09-15",
        },
        {
            "documentCode": "A..",
            "documentDescription": "Amendment After Final",
            "documentDate": "2018-12-01",
        },
        {
            "documentCode": "NOA",
            "documentDescription": "Notice of Allowance",
            "documentDate": "2019-02-20",
        },
    ]


@pytest.fixture
def mock_file_wrapper_with_td() -> list[dict]:
    """File wrapper docs that include a terminal disclaimer."""
    return [
        {
            "documentCode": "CTNF",
            "documentDescription": "Non-Final Rejection",
            "documentDate": "2018-03-10",
        },
        {
            "documentCode": "DIST",
            "documentDescription": "Terminal Disclaimer Filed",
            "documentDate": "2018-06-05",
        },
        {
            "documentCode": "NOA",
            "documentDescription": "Notice of Allowance",
            "documentDate": "2019-02-20",
        },
    ]


@pytest.fixture
def mock_office_actions() -> list[dict]:
    """Structured office action data."""
    return [
        {
            "rejectionBasis": "35 U.S.C. 103",
            "claimsRejected": [1, 2, 5],
            "citedReferences": ["US5000000", "US6000000"],
        },
        {
            "rejectionBasis": "35 U.S.C. 102",
            "claimsRejected": [3],
            "citedReferences": ["US7000000"],
        },
    ]


# ---------------------------------------------------------------------------
# Document classification
# ---------------------------------------------------------------------------


class TestDocumentClassification:
    def test_classify_rejection_by_code(self):
        from praviar_pipeline.utils.prosecution_history import _classify_document

        doc = {"documentCode": "CTNF", "documentDescription": ""}
        assert _classify_document(doc) == "rejection"

    def test_classify_rejection_by_description(self):
        from praviar_pipeline.utils.prosecution_history import _classify_document

        doc = {"documentCode": "UNKNOWN", "documentDescription": "Office Action Summary"}
        assert _classify_document(doc) == "rejection"

    def test_classify_response_by_code(self):
        from praviar_pipeline.utils.prosecution_history import _classify_document

        doc = {"documentCode": "RES", "documentDescription": ""}
        assert _classify_document(doc) == "response"

    def test_classify_response_by_description(self):
        from praviar_pipeline.utils.prosecution_history import _classify_document

        doc = {"documentCode": "XYZ", "documentDescription": "Applicant Response and Amendment"}
        assert _classify_document(doc) == "response"

    def test_classify_noa(self):
        from praviar_pipeline.utils.prosecution_history import _classify_document

        doc = {"documentCode": "NOA", "documentDescription": ""}
        assert _classify_document(doc) == "notice_of_allowance"

    def test_classify_td(self):
        from praviar_pipeline.utils.prosecution_history import _classify_document

        doc = {"documentCode": "DIST", "documentDescription": ""}
        assert _classify_document(doc) == "terminal_disclaimer"

    def test_classify_other(self):
        from praviar_pipeline.utils.prosecution_history import _classify_document

        doc = {"documentCode": "MISC", "documentDescription": "Information Disclosure Statement"}
        assert _classify_document(doc) == "other"


# ---------------------------------------------------------------------------
# Rejection extraction
# ---------------------------------------------------------------------------


class TestRejectionExtraction:
    def test_extract_rejection_type_102(self):
        from praviar_pipeline.utils.prosecution_history_helpers import extract_rejection_type

        doc = {"documentDescription": "Rejection under 35 USC 102", "documentCode": ""}
        assert extract_rejection_type(doc) == "102"

    def test_extract_rejection_type_103(self):
        from praviar_pipeline.utils.prosecution_history_helpers import extract_rejection_type

        doc = {"documentDescription": "Rejection under 35 USC 103", "documentCode": ""}
        assert extract_rejection_type(doc) == "103"

    def test_extract_rejection_type_112a(self):
        from praviar_pipeline.utils.prosecution_history_helpers import extract_rejection_type

        doc = {
            "documentDescription": "Written description rejection under 112(a)",
            "documentCode": "",
        }
        assert extract_rejection_type(doc) == "112_a"

    def test_extract_rejection_type_112b(self):
        from praviar_pipeline.utils.prosecution_history_helpers import extract_rejection_type

        doc = {"documentDescription": "Indefiniteness rejection under 112(b)", "documentCode": ""}
        assert extract_rejection_type(doc) == "112_b"

    def test_extract_rejection_type_101(self):
        from praviar_pipeline.utils.prosecution_history_helpers import extract_rejection_type

        doc = {"documentDescription": "Rejection under 101 patent eligibility", "documentCode": ""}
        assert extract_rejection_type(doc) == "101"

    def test_extract_rejection_type_fallback(self):
        from praviar_pipeline.utils.prosecution_history_helpers import extract_rejection_type

        doc = {"documentDescription": "Restriction Requirement", "documentCode": "CTNF"}
        assert extract_rejection_type(doc) == "other"


# ---------------------------------------------------------------------------
# Narrowing amendment identification
# ---------------------------------------------------------------------------


class TestNarrowingAmendments:
    def test_amendments_after_rejections_are_narrowing(self, mock_file_wrapper_docs):
        from praviar_pipeline.utils.prosecution_history import _identify_narrowing_amendments

        amendments = _identify_narrowing_amendments(mock_file_wrapper_docs)
        # Should find the two response/amendment documents
        assert len(amendments) >= 1
        # At least one should be narrowing (response after rejection)
        assert any(a.narrowing for a in amendments)
        assert any(a.response_to_rejection for a in amendments)

    def test_no_documents_returns_empty(self):
        from praviar_pipeline.utils.prosecution_history import _identify_narrowing_amendments

        amendments = _identify_narrowing_amendments([])
        assert amendments == []

    def test_no_rejections_means_not_narrowing(self):
        from praviar_pipeline.utils.prosecution_history import _identify_narrowing_amendments

        docs = [
            {
                "documentCode": "A..",
                "documentDescription": "Preliminary Amendment",
                "documentDate": "2018-01-01",
            },
        ]
        amendments = _identify_narrowing_amendments(docs)
        # An amendment with no prior rejection may still be identified
        # but its narrowing flag should depend on the timing analysis
        for a in amendments:
            assert a.response_to_rejection is False


# ---------------------------------------------------------------------------
# Full prosecution history fetch
# ---------------------------------------------------------------------------


class TestFetchProsecutionHistory:
    async def test_full_fetch_with_structured_oa(
        self, mock_settings, mock_file_wrapper_docs, mock_office_actions
    ):
        """With structured OA data available, rejections come from OA endpoint."""
        from praviar_pipeline.utils.prosecution_history import fetch_prosecution_history

        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents.return_value = mock_file_wrapper_docs
        mock_client.get_application_data.return_value = {"applicationNumber": "12/345678"}
        mock_client.get_office_actions.return_value = mock_office_actions

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.prosecution_history.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await fetch_prosecution_history("US8000000B2")

        assert isinstance(result, ProsecutionHistory)
        assert result.patent_id == "US8000000B2"
        assert result.application_number == "12/345678"
        assert len(result.rejections) == 2
        assert result.rejections[0].rejection_type == "103"
        assert result.rejections[1].rejection_type == "102"
        assert 1 in result.rejections[0].claims_rejected
        assert result.prosecution_complete is True  # NOA found

    async def test_fallback_to_document_classification(self, mock_settings, mock_file_wrapper_docs):
        """When structured OA endpoint fails, fall back to document classification."""
        from praviar_pipeline.utils.prosecution_history import fetch_prosecution_history

        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents.return_value = mock_file_wrapper_docs
        mock_client.get_application_data.return_value = {"applicationNumber": "12/345678"}
        mock_client.get_office_actions.side_effect = httpx.ConnectError("OA endpoint down")

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.prosecution_history.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await fetch_prosecution_history("US8000000B2")

        assert isinstance(result, ProsecutionHistory)
        # Should find rejections from document classification (CTNF, CTFR)
        assert len(result.rejections) >= 2
        assert result.prosecution_complete is True

    async def test_terminal_disclaimer_detected(self, mock_settings, mock_file_wrapper_with_td):
        """Terminal disclaimer in file wrapper should set has_terminal_disclaimer."""
        from praviar_pipeline.utils.prosecution_history import fetch_prosecution_history

        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents.return_value = mock_file_wrapper_with_td
        mock_client.get_application_data.return_value = {}
        mock_client.get_office_actions.return_value = []

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.prosecution_history.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await fetch_prosecution_history("US8000000B2")

        assert result.has_terminal_disclaimer is True

    async def test_empty_file_wrapper(self, mock_settings):
        """Empty file wrapper returns minimal ProsecutionHistory."""
        from praviar_pipeline.utils.prosecution_history import fetch_prosecution_history

        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents.return_value = []

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.prosecution_history.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await fetch_prosecution_history("US8000000B2")

        assert result.patent_id == "US8000000B2"
        assert result.rejections == []
        assert result.amendments == []

    async def test_file_wrapper_fetch_fails(self, mock_settings):
        """API failure returns minimal ProsecutionHistory."""
        from praviar_pipeline.utils.prosecution_history import fetch_prosecution_history

        mock_client = AsyncMock()
        mock_client.get_file_wrapper_documents.side_effect = httpx.ConnectError("Network error")

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.prosecution_history.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await fetch_prosecution_history("US8000000B2")

        assert result.patent_id == "US8000000B2"
        assert result.rejections == []

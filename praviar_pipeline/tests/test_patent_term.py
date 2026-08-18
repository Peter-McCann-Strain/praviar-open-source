"""Tests for patent term calculator with mocked USPTO API."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from praviar_pipeline.errors import InsufficientDataError, SourceUnavailableError
from praviar_pipeline.models.patent import PatentTermInfo

PTA_TERMINAL_DISCLAIMER_AUTHORITY = (
    "https://uscode.house.gov/view.xhtml?req=(title:35%20section:154%20edition:prelim)"
)
PTE_TERMINAL_DISCLAIMER_AUTHORITY = "https://www.cafc.uscourts.gov/opinions-orders/06-1401.pdf"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_app_data() -> dict:
    """Minimal application data returned by USPTOODPClient.get_application_data()."""
    return {
        "applicationNumber": "12/345678",
        "filingDate": "2010-03-15",
        "grantDate": "2012-06-20",
        "patentTermAdjustmentDays": 120,
    }


@pytest.fixture
def mock_continuity_data() -> list[dict]:
    """Continuity chain — the patent is a continuation of an earlier application."""
    return [
        {
            "parentApplicationNumber": "11/111111",
            "parentFilingDate": "2008-01-10",
            "claimType": "continuation",
        },
    ]


@pytest.fixture
def mock_empty_continuity() -> list[dict]:
    return []


@pytest.fixture
def mock_td_documents() -> list[dict]:
    """File wrapper documents with a terminal disclaimer."""
    return [
        {
            "documentCode": "CTNF",
            "documentDescription": "Non-Final Rejection",
        },
        {
            "documentCode": "DIST",
            "documentDescription": "Terminal Disclaimer Filed",
            "linkedPatentNumber": "US7000000B2",
        },
    ]


@pytest.fixture
def mock_no_td_documents() -> list[dict]:
    """File wrapper documents without a terminal disclaimer."""
    return [
        {
            "documentCode": "CTNF",
            "documentDescription": "Non-Final Rejection",
        },
        {
            "documentCode": "NOA",
            "documentDescription": "Notice of Allowance",
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBaseTerm:
    async def test_base_term_computation(
        self, mock_settings, mock_app_data, mock_empty_continuity, mock_no_td_documents
    ):
        """Base expiry = filing date + 20 years."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = mock_app_data
        mock_client.get_continuity_data.return_value = mock_empty_continuity
        mock_client.get_file_wrapper_documents.return_value = mock_no_td_documents

        # Mock the context manager
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2")

        assert isinstance(result, PatentTermInfo)
        assert result.patent_id == "US8000000B2"
        # Filing date 2010-03-15 + 20 years = 2030-03-15
        assert result.effective_filing_date == date(2010, 3, 15)
        assert result.base_expiry == date(2030, 3, 15)
        assert result.grant_date == date(2012, 6, 20)

    async def test_continuity_chain_adjusts_effective_filing(
        self, mock_settings, mock_app_data, mock_continuity_data, mock_no_td_documents
    ):
        """Continuity chain should walk to earliest parent filing date."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = mock_app_data
        mock_client.get_continuity_data.return_value = mock_continuity_data
        mock_client.get_file_wrapper_documents.return_value = mock_no_td_documents

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2")

        # Parent filing date 2008-01-10 is earlier, so effective filing adjusts
        assert result.effective_filing_date == date(2008, 1, 10)
        # Base expiry = 2008-01-10 + 20 = 2028-01-10
        assert result.base_expiry == date(2028, 1, 10)


class TestPTAAdjustment:
    async def test_pta_adds_days_to_adjusted_expiry(
        self, mock_settings, mock_app_data, mock_empty_continuity, mock_no_td_documents
    ):
        """PTA days should be reflected in the adjusted_expiry."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = mock_app_data
        mock_client.get_continuity_data.return_value = mock_empty_continuity
        mock_client.get_file_wrapper_documents.return_value = mock_no_td_documents

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2")

        assert result.pta_days == 120
        expected_adjusted = date(2030, 3, 15) + timedelta(days=120)
        assert result.adjusted_expiry == expected_adjusted
        assert any("PTA" in note for note in result.calculation_notes)

    async def test_zero_pta(self, mock_settings, mock_empty_continuity, mock_no_td_documents):
        """When PTA is 0, adjusted_expiry == base_expiry."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        app_data = {
            "applicationNumber": "12/345678",
            "filingDate": "2015-06-01",
            "grantDate": "2017-09-01",
            "patentTermAdjustmentDays": 0,
        }
        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = app_data
        mock_client.get_continuity_data.return_value = mock_empty_continuity
        mock_client.get_file_wrapper_documents.return_value = mock_no_td_documents

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US9000000B2")

        assert result.pta_days == 0
        assert result.base_expiry == date(2035, 6, 1)
        assert result.adjusted_expiry == date(2035, 6, 1)


class TestTerminalDisclaimer:
    async def test_td_detected(
        self,
        mock_settings,
        mock_app_data,
        mock_empty_continuity,
        mock_td_documents,
        mock_no_td_documents,
    ):
        """Terminal disclaimer should be detected from file wrapper."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = mock_app_data
        mock_client.get_continuity_data.return_value = mock_empty_continuity
        mock_client.get_file_wrapper_documents.side_effect = lambda patent_id: (
            mock_td_documents if patent_id == "US8000000B2" else mock_no_td_documents
        )

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2")

        assert result.terminal_disclaimer is True
        assert result.td_linked_expiry is not None
        assert any("terminal disclaimer" in note.lower() for note in result.calculation_notes)

    async def test_pta_is_capped_by_td_before_section_156_pte(self, mock_settings):
        """Apply §154(b)(2)(B), then §156 as construed in Merck v. Hi-Tech.

        Primary authorities: PTA_TERMINAL_DISCLAIMER_AUTHORITY and
        PTE_TERMINAL_DISCLAIMER_AUTHORITY.
        """
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        application_data = {
            "US8000000B2": {
                "filingDate": "2010-01-01",
                "grantDate": "2012-01-01",
                "patentTermAdjustmentDays": 730,
                "patentTermExtensionDays": 365,
            },
            "US7000000B2": {
                "filingDate": "2009-01-01",
                "grantDate": "2011-01-01",
                "patentTermAdjustmentDays": 0,
                "patentTermExtensionDays": 0,
            },
        }
        td_documents = [
            {
                "documentCode": "DIST",
                "documentDescription": "Terminal Disclaimer Filed",
                "linkedPatentNumber": "US7000000B2",
            }
        ]
        mock_client = AsyncMock()
        mock_client.get_application_data.side_effect = lambda patent_id: application_data[patent_id]
        mock_client.get_continuity_data.return_value = []
        mock_client.get_file_wrapper_documents.side_effect = lambda patent_id: (
            td_documents if patent_id == "US8000000B2" else []
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2")

        assert PTA_TERMINAL_DISCLAIMER_AUTHORITY.startswith("https://uscode.house.gov/")
        assert PTE_TERMINAL_DISCLAIMER_AUTHORITY.startswith("https://www.cafc.uscourts.gov/")
        assert result.base_expiry == date(2030, 1, 1)
        assert result.pta_days == 730
        assert result.td_linked_expiry == date(2029, 1, 1)
        assert result.pte_extension_base_expiry == date(2029, 1, 1)
        assert result.adjusted_expiry == date(2030, 1, 1)

    async def test_linked_td_cycle_typed_fails(self, mock_settings):
        """Visited state must propagate through A→B→A linked-TD recursion."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = {
            "filingDate": "2010-01-01",
            "grantDate": "2012-01-01",
        }
        mock_client.get_continuity_data.return_value = []
        mock_client.get_file_wrapper_documents.side_effect = lambda patent_id: [
            {
                "documentCode": "DIST",
                "documentDescription": "Terminal Disclaimer Filed",
                "linkedPatentNumber": (
                    "US7000000B2" if patent_id == "US8000000B2" else "US8000000B2"
                ),
            }
        ]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.utils.patent_term.USPTOODPClient",
                return_value=mock_client,
            ),
            pytest.raises(InsufficientDataError, match="cycle"),
        ):
            await calculate_patent_term("US8000000B2")

    async def test_no_td(
        self, mock_settings, mock_app_data, mock_empty_continuity, mock_no_td_documents
    ):
        """No terminal disclaimer should result in terminal_disclaimer=False."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = mock_app_data
        mock_client.get_continuity_data.return_value = mock_empty_continuity
        mock_client.get_file_wrapper_documents.return_value = mock_no_td_documents

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2")

        assert result.terminal_disclaimer is False


class TestMaintenanceFeeLapse:
    async def test_lapsed_maintenance_fee(
        self, mock_settings, mock_app_data, mock_empty_continuity, mock_no_td_documents
    ):
        """Maintenance fee lapse detected from legal events."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        legal_events = [
            {
                "event_description": "Patent lapsed due to non-payment of maintenance fee",
                "event_code": "LAPS",
                "event_date": date(2024, 6, 1),
            },
        ]

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = mock_app_data
        mock_client.get_continuity_data.return_value = mock_empty_continuity
        mock_client.get_file_wrapper_documents.return_value = mock_no_td_documents

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2", legal_events=legal_events)

        assert result.maintenance_fee_status == "lapsed"
        assert any("lapsed" in note.lower() for note in result.calculation_notes)

    async def test_no_legal_events(
        self, mock_settings, mock_app_data, mock_empty_continuity, mock_no_td_documents
    ):
        """Without legal events, maintenance fee status remains unknown."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = mock_app_data
        mock_client.get_continuity_data.return_value = mock_empty_continuity
        mock_client.get_file_wrapper_documents.return_value = mock_no_td_documents

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "praviar_pipeline.utils.patent_term.USPTOODPClient",
            return_value=mock_client,
        ):
            result = await calculate_patent_term("US8000000B2")

        assert result.maintenance_fee_status == "unknown"


class TestAppDataFailure:
    async def test_app_data_fetch_fails(self, mock_settings):
        """Provider failure is uncovered, never an empty successful calculation."""
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.side_effect = httpx.ConnectError("API down")

        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.utils.patent_term.USPTOODPClient",
                return_value=mock_client,
            ),
            pytest.raises(SourceUnavailableError, match="patent-term application fetch failed"),
        ):
            await calculate_patent_term("US8000000B2")

    async def test_empty_app_data_typed_fails(self, mock_settings):
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = {}
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.utils.patent_term.USPTOODPClient",
                return_value=mock_client,
            ),
            pytest.raises(SourceUnavailableError, match="application data was empty"),
        ):
            await calculate_patent_term("US8000000B2")

    async def test_unparseable_filing_data_typed_fails(self, mock_settings):
        from praviar_pipeline.utils.patent_term import calculate_patent_term

        mock_client = AsyncMock()
        mock_client.get_application_data.return_value = {"filingDate": "not-a-date"}
        mock_client.get_continuity_data.return_value = []
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "praviar_pipeline.utils.patent_term.USPTOODPClient",
                return_value=mock_client,
            ),
            pytest.raises(InsufficientDataError),
        ):
            await calculate_patent_term("US8000000B2")

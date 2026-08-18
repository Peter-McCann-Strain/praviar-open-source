"""Tests for prosecution-history preparation helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from praviar_pipeline.errors import SourceUnavailableError
from praviar_pipeline.pipeline.analysis.prosecution import fetch_prosecution_context_impl


@pytest.mark.asyncio
async def test_fetch_prosecution_context_skips_non_us_patent(mock_settings) -> None:
    assert await fetch_prosecution_context_impl("EP123") == {}


@pytest.mark.asyncio
async def test_fetch_prosecution_context_formats_sections(mock_settings) -> None:
    odp = AsyncMock()
    odp.get_office_actions.return_value = [
        {
            "documentCode": "NFOA",
            "documentDescription": "Non-Final Office Action",
            "mailDate": "2024-01-01",
        }
    ]
    odp.get_continuity_data.return_value = [
        {
            "parentApplicationNumberText": "123456",
            "claimTypeCd": "CIP",
            "filingDate": "2024-01-02",
        }
    ]
    odp.get_transactions.return_value = [
        {
            "transactionCode": "AMND",
            "transactionDescription": "Amendment filed",
            "transactionDate": "2024-01-03",
        }
    ]
    odp.get_file_wrapper_documents.return_value = [
        {"documentIdentifier": "FW1"},
        {"documentIdentifier": "FW2"},
    ]
    odp.__aenter__.return_value = odp
    odp.__aexit__.return_value = False

    with patch("praviar_pipeline.clients.uspto_odp.USPTOODPClient", return_value=odp):
        result = await fetch_prosecution_context_impl("US123")

    assert result["office_actions"] == "- [NFOA] Non-Final Office Action (2024-01-01)"
    assert result["continuity"] == "- Parent: 123456 (CIP, filed 2024-01-02)"
    assert result["amendments"] == "- [AMND] Amendment filed (2024-01-03)"
    assert result["sections_available"] == [
        "office_actions",
        "continuity",
        "amendments",
        "us_file_wrapper_dossier",
    ]
    assert result["file_wrapper_document_count"] == 2
    assert result["office_action_count"] == 1
    assert result["continuity_entry_count"] == 1
    assert result["amendment_entry_count"] == 1
    assert result["office_action_types"] == ["non_final_office_action"]
    assert result["amendment_types"] == ["amendment"]
    assert result["continuity_types"] == ["cip"]
    assert result["estoppel_risk_flags"] == [
        "cip_lineage",
        "amendment_after_office_action_history",
    ]
    assert result["office_action_events"][0]["document_code"] == "NFOA"
    assert result["continuity_entries"][0]["continuity_type"] == "cip"
    assert result["amendment_events"][0]["event_type"] == "amendment"


@pytest.mark.asyncio
async def test_fetch_prosecution_context_fails_closed_on_client_error(mock_settings) -> None:
    with patch(
        "praviar_pipeline.clients.uspto_odp.USPTOODPClient", side_effect=RuntimeError("boom")
    ):
        with pytest.raises(SourceUnavailableError):
            await fetch_prosecution_context_impl("US123")
